#!/usr/bin/env python
# -*- coding: utf-8 -*-

#
#  This file is part of the `pypath` python module
#
#  Copyright
#  2014-2019
#  EMBL, EMBL-EBI, Uniklinik RWTH Aachen, Heidelberg University
#
#  File author(s): Dénes Türei (turei.denes@gmail.com)
#                  Nicolàs Palacio
#                  Olga Ivanova
#
#  Distributed under the GPLv3 License.
#  See accompanying file LICENSE.txt or copy at
#      http://www.gnu.org/licenses/gpl-3.0.html
#
#  Website: http://pypath.omnipathdb.org/
#

from future.utils import iteritems

import importlib as imp
import collections
import operator
import itertools
import functools

import pypath.evidence as pypath_evidence
import pypath.resource as pypath_resource
import pypath.session_mod as session_mod
import pypath.common as common
import pypath.mapping as mapping
import pypath.entity as entity

_logger = session_mod.Logger(name = 'interaction')
_log = _logger._log


InteractionKey = collections.namedtuple(
    'InteractionKey',
    [
        'entity_a',
        'entity_b',
    ],
)


class Interaction(object):
    
    
    def __init__(
            self,
            a,
            b,
            id_type_a = 'uniprot',
            id_type_b = 'uniprot',
            entity_type_a = 'protein',
            entity_type_b = 'protein',
            taxon_a = 9606,
            taxon_b = 9606,
        ):
        
        a = self._get_entity(
            identifier = a,
            id_type = id_type_a,
            entity_type = entity_type_a,
            taxon = taxon_a,
        )
        b = self._get_entity(
            identifier = b,
            id_type = id_type_b,
            entity_type = entity_type_b,
            taxon = taxon_b,
        )
        
        self.nodes = tuple(sorted((a, b)))
        self.a = self.nodes[0]
        self.b = self.nodes[1]
        
        self.key = self._key
        
        self.a_b = (self.nodes[0], self.nodes[1])
        self.b_a = (self.nodes[1], self.nodes[0])
        
        self.evidences = pypath_evidence.Evidences()
        self.direction = {
            self.a_b: pypath_evidence.Evidences(),
            self.b_a: pypath_evidence.Evidences(),
            'undirected': pypath_evidence.Evidences(),
        }
        self.positive = {
            self.a_b: pypath_evidence.Evidences(),
            self.b_a: pypath_evidence.Evidences(),
        }
        self.negative = {
            self.a_b: pypath_evidence.Evidences(),
            self.b_a: pypath_evidence.Evidences(),
        }
    
    
    def reload(self):
        """
        Reloads the object from the module level.
        """

        modname = self.__class__.__module__
        evmodname = self.evidences.__class__.__module__
        enmodname = self.a.__class__.__module__
        mod = __import__(modname, fromlist = [modname.split('.')[0]])
        evmod = __import__(evmodname, fromlist = [evmodname.split('.')[0]])
        enmod = __import__(enmodname, fromlist = [enmodname.split('.')[0]])
        imp.reload(mod)
        imp.reload(evmod)
        imp.reload(enmod)
        new = getattr(mod, self.__class__.__name__)
        evsnew = getattr(evmod, 'Evidences')
        evnew = getattr(evmod, 'Evidence')
        ennew = getattr(enmod, 'Entity')
        setattr(self, '__class__', new)
        
        for evs in itertools.chain(
            (self.evidences,),
            self.direction.values(),
            self.positive.values(),
            self.negative.values(),
        ):
            
            evs.__class__ = evsnew
            
            for ev in evs:
                
                ev.__class__ = evnew
        
        self.a.__class__ = ennew
        self.b.__class__ = ennew


    def _get_entity(
            self,
            identifier,
            id_type = 'uniprot',
            entity_type = 'protein',
            taxon = 9606,
        ):
        
        if not isinstance(identifier, entity.Entity):
            
            identifier = entity.Entity(
                identifier = identifier,
                id_type = id_type,
                entity_type = entity_type,
                taxon = taxon,
            )
        
        return identifier


    def _check_nodes_key(self, nodes):
        """Checks if *nodes* is contained in the edge.

        :arg list nodes:
             Or [tuple], contains the names of the nodes to be checked.

        :return:
            (*bool*) -- ``True`` if all elements in *nodes* are
            contained in the object :py:attr:`nodes` list.
        """

        return nodes == self.a_b or nodes == self.b_a


    def _check_direction_key(self, direction):
        """
        Checks if *direction* is ``'undirected'`` or contains the nodes of
        the current edge. Used internally to check that *di* is a valid
        key for the object attributes declared on dictionaries.

        :arg tuple di:
            Or [str], key to be tested for validity.

        :return:
            (*bool*) -- ``True`` if *di* is ``'undirected'`` or a tuple
              of node names contained in the edge, ``False`` otherwise.
        """

        return (
            direction == 'undirected' or (
                isinstance(direction, tuple) and
                self._check_nodes_key(direction)
            )
        )


    def id_to_entity(self, identifier):
        
        return (
            self.a
                if self.a == identifier else
            self.b
                if self.b == identifier else
            None
        )


    def direction_key(self, direction):
        
        if direction == 'undirected':
            
            return direction
        
        direction = tuple(map(self.id_to_entity, direction))
        
        return (
            direction
                if direction == self.a_b or direction == self.b_a else
            None
        )
    
    
    def _directed_key(self, direction):
        
        return direction is not None and direction != 'undirected'


    def add_evidence(
            self,
            evidence,
            direction = 'undirected',
            effect = 0,
            references = None,
        ):
        """
        Adds directionality information with the corresponding data
        source named. Modifies self attributes :py:attr:`dirs` and
        :py:attr:`sources`.

        :arg resource.NetworkResource,evidence.Evidence evidence:
            Either a ``pypath.evidence.Evidence`` object or a resource as
            ``pypath.resource.NetworkResource`` object. In the latter case
            the references can be provided in a separate argument.
        :arg tuple direction:
            Or [str], the directionality key for which the value on
            :py:attr:`dirs` has to be set ``True``.
        :arg int effect:
            The causal effect of the interaction. 1 or 'stimulation'
            corresponds to a stimulatory, -1 or 'inhibition' to an
            inhibitory while 0 to an unknown or neutral effect.
        :arg set,NoneType references:
            A set of references, used only if the resource have been provided
            as ``NetworkResource`` object.
        """
        
        direction = self.direction_key(direction)
        
        if direction is None:
            
            _log(
                'Attempting to add evidence with non matching '
                'interaction partners.'
            )
            return
        
        evidence = (
            evidence
                if isinstance(
                    evidence,
                    (
                        pypath_evidence.Evidence,
                        pypath_evidence.Evidences,
                    )
                ) else
            pypath_evidence.Evidence(
                resource = evidence,
                references = references,
            )
        )
        
        self.evidences += evidence
        self.direction[direction] += evidence
        
        if direction != 'undirected':
            
            if effect in {1, 'positive', 'stimulation'}:
                
                self.positive[direction] += evidence
            
            elif effect in {-1, 'negative', 'inhibition'}:
                
                self.negative[direction] += evidence
    
    
    def __hash__(self):
        
        return hash(self.key)
    
    
    def __eq__(self, other):
        
        return self.key == other.key
    
    
    @property
    def _key(self):
        
        return InteractionKey(
            self.a.key,
            self.b.key,
        )


    def __iadd__(self, other):
        
        if self != other:
            
            _log(
                'Attempt to merge interactions with '
                'non matching interaction partners.'
            )
            return self
        
        self._merge_evidences(self, other)
        
        return self
    
    
    def __add__(self, other):
        
        new = self.__copy__()
        
        new += other
        
        return new
    
    
    def __copy__(self):
        
        new = Interaction(*self.key)
        new += self
        
        return new
    
    
    @staticmethod
    def _merge_evidences(one, other):
        
        one.evidences += other.evidences
        
        for dir_key in one.direction.keys():
            
            one.direction[dir_key] += other.direction[dir_key]
        
        for eff_key in one.positive.keys():
            
            one.positive[eff_key] += other.positive[eff_key]
        
        for eff_key in one.negative.keys():
            
            one.negative[eff_key] += other.negative[eff_key]
    
    
    def __repr__(self):
        
        return '<Interaction: %s %s=%s=%s=%s %s [%s]>' % (
            self.a.label or self.a.identifier,
            '<' if self.direction[self.b_a] else '=',
            (
                '(+-)' if (
                    self.positive[self.b_a] and
                    self.negative[self.b_a]
                ) else
                '(+)=' if self.positive[self.b_a] else
                '(-)=' if self.negative[self.b_a] else
                '===='
            ),
            (
                '(+-)' if (
                    self.positive[self.a_b] and
                    self.negative[self.a_b]
                ) else
                '(+)=' if self.positive[self.a_b] else
                '(-)=' if self.negative[self.a_b] else
                '===='
            ),
            '>' if self.direction[self.a_b] else '=',
            self.b.label or self.b.identifier,
            self.evidences.__repr__().strip('<>'),
        )
    
    
    def __contains__(self, other):
        
        return self.evidences.__contains__(other)
    
    
    def has_data_model(self, data_model):
        
        return self.evidences.has_data_model(data_model)
    
    
    @property
    def data_models(self):
        
        return {
            ev.resource.data_model
            for ev in self.evidences
        }


    def get_direction(
            self,
            direction,
            resources = False,
            evidences = False,
            sources = False,
            resource_names = False,
        ):
        """
        Returns the state (or *resources* if specified) of the given
        *direction*.

        :arg tuple direction:
            Or [str] (if ``'undirected'``). Pair of nodes from which
            direction information is to be retrieved.
        :arg bool resources:
            Optional, ``'False'`` by default. Specifies if the
            :py:attr:`resources` information of the given direction is to
            be retrieved instead.

        :return:
            (*bool* or *set*) -- (if ``resources=True``). Presence/absence
            of the requested direction (or the list of resources if
            specified). Returns ``None`` if *direction* is not valid.
        """
        
        direction = self.direction_key(direction)
        
        if direction is not None:
            
            return self._select_answer_type(
                self.direction[direction],
                resources = resources,
                evidences = evidences,
                resource_names = resource_names,
                sources = sources,
            )

        else:
            return None


    def get_directions(
            self,
            src,
            tgt,
            resources = False,
            evidences = False,
            resource_names = False,
            sources = False,
        ):
        """
        Returns all directions with boolean values or list of sources.

        :arg str src:
            Source node.
        :arg str tgt:
            Target node.
        :arg bool resources:
            Optional, ``False`` by default. Specifies whether to return
            the :py:attr:`resources` attribute instead of :py:attr:`dirs`.

        :return:
            Contains the :py:attr:`dirs` (or :py:attr:`resources` if
            specified) of the given edge.
        """

        query = (src, tgt)
        
        answer_type_args = {
            'resources': resources,
            'evidences': evidences,
            'resource_names': resource_names,
            'sources': sources,
        }
        
        query = self.direction_key(query)
        
        if query is not None:
            
            return [
                self._select_answer_type(
                    self.direction[query],
                    **answer_type_args
                ),
                self._select_answer_type(
                    self.direction[tuple(reversed(query))],
                    **answer_type_args
                ),
                self._select_answer_type(
                    self.direction['undirected'],
                    **answer_type_args
                ),
            ]
            
        else:
            return None


    def _select_answer_type(
            self,
            answer,
            resources = False,
            evidences = False,
            resource_names = False,
            sources = False,
        ):
        
        return (
            answer
                if evidences else
            answer.get_resources()
                if resources else
            answer.get_resource_names()
                if sources or resource_names else
            bool(answer)
        )


    def which_directions(
            self,
            resources = None,
            effect = None,
        ):
        """
        Returns the pair(s) of nodes for which there is information
        about their directionality.

        :arg str effect:
            Either *positive* or *negative*.
        :arg str,set resources:
            Limits the query to one or more resources. Optional.

        :return:
            (*tuple*) -- Tuple of tuples with pairs of nodes where the
            first element is the source and the second is the target
            entity, according to the given resources and limited to the
            effect.
        """

        resources = self._resources_set(resources)
        effect = self._effect_synonyms(effect)

        return tuple(
            _dir
            for _dir, _evidences in iteritems(self.direction)
            if _dir != 'undirected' and
            _evidences and (
                not resources or
                _evidences & resources
            ) and (
                not effect
                or (
                    not resources and
                    getattr(self, effect)
                ) or
                getattr(self, effect) & resources
            )
        )


    # synonym: old name
    which_dirs = which_directions


    def which_signs(self, resources = None, effect = None):
        """
        Returns the pair(s) of nodes for which there is information
        about their effect signs.

        :param str,set resources:
            Limits the query to one or more resources. Optional.
        :param str effect:
            Either *positive* or *negative*, limiting the query to positive
            or negative effects; for any other values effects of both
            signs will be returned.

        :return:
            (*tuple*) -- Tuple of tuples with pairs of nodes where the
            first element is a tuple of the source and the target entity,
            while the second element is the effect sign, according to
            the given resources. E.g. ((('A', 'B'), 'positive'),)
        """

        resources = self._resources_set(resources)
        effect = self._effect_synonyms(effect)
        effects = (effect,) if effect else ('positive', 'negative')

        return tuple(
            (_dir, _effect)
            for _effect in effects
            for _dir, _evidences in iteritems(getattr(self, _effect))
            if _evidences and (
                not resources or
                _evidences & resources
            )
        )


    @staticmethod
    def _effect_synonyms(effect):

        if not effect:

            return

        if effect in {'positive', 'stimulation', 'stimulatory'}:

            return 'positive'

        if effect in {'negative', 'inhibition', 'inhibitory'}:

            return 'negative'


    def _resources_set(self, resources = None):

        return common.to_set(resources)


    def unset_direction(
            self,
            direction,
            only_sign = False,
            resource = None,
            interaction_type = None,
            via = False,
            source = None,
        ):
        """
        Removes directionality and/or source information of the
        specified *direction*. Modifies attribute :py:attr:`dirs` and
        :py:attr:`sources`.

        :arg tuple direction:
            Or [str] (if ``'undirected'``) the pair of nodes specifying
            the directionality from which the information is to be
            removed.
        :arg set resource:
            Optional, ``None`` by default. If specified, determines
            which specific source(s) is(are) to be removed from
            :py:attr:`sources` attribute in the specified *direction*.
        """
        
        direction = self.direction_key(direction)
        
        if direction is not None:
            
            attrs = (
                (self._effect_synonyms(only_sign),)
                    if only_sign else
                ('direction', 'positive', 'negative')
            )
            resource = resource or source
            
            for attr in attrs:
                
                if resource is not None:
                    
                    getattr(self, attr)[direction].remove(
                        resource = resource,
                        interaction_type = interaction_type,
                        via = via,
                    )
                    
                else:
                    getattr(self, attr)[direction] = (
                        pypath_evidence.Evidences()
                    )


    # synonym: old name
    unset_dir = unset_direction


    def unset_sign(
            self,
            direction,
            sign,
            resource = None,
            interaction_type = None,
            via = False,
            source = None,
        ):
        """
        Removes sign and/or source information of the specified
        *direction* and *sign*. Modifies attribute :py:attr:`positive`
        and :py:attr:`positive_sources` or :py:attr:`negative` and
        :py:attr:`negative_sources` (or
        :py:attr:`positive_attributes`/:py:attr:`negative_sources`
        only if ``source=True``).

        :arg tuple direction:
            The pair of nodes specifying the directionality from which
            the information is to be removed.
        :arg str sign:
            Sign from which the information is to be removed. Must be
            either ``'positive'`` or ``'negative'``.
        :arg set source:
            Optional, ``None`` by default. If specified, determines
            which source(s) is(are) to be removed from the sources in
            the specified *direction* and *sign*.
        """
        
        self.unset_direction(
            direction = direction,
            only_sign = sign,
            resource = resource,
            interaction_type = interaction_type,
            via = via,
            source = source,
        )


    def is_directed(self):
        """
        Checks if edge has any directionality information.

        :return:
            (*bool*) -- Returns ``True`` if any of the :py:attr:`dirs`
            attribute values is ``True`` (except ``'undirected'``),
            ``False`` otherwise.
        """

        return any(self.direction.values())


    def is_directed_by_resources(self, resources = None):
        """
        Checks if edge has any directionality information from some
        resource(s).

        :return:
            (*bool*) -- Returns ``True`` if any of the :py:attr:`dirs`
            attribute values is ``True`` (except ``'undirected'``),
            ``False`` otherwise.
        """

        return self._by_resource(resources, op = operator.or_)


    def is_mutual(self, resources = None):
        """
        Checks if the edge has mutual directions (both A-->B and B-->A).
        """

        return (
            bool(self.direction[self.a_b]) and bool(self.direction[self.b_a])
                if not resources else
            self.is_mutual_by_resources(resources = resources)
        )


    def is_mutual_by_resources(self, resources = None):
        """
        Checks if the edge has mutual directions (both A-->B and B-->A)
        according to some resource(s).
        """

        return self._by_resource(resources, op = operator.and_)


    def _by_resource(self, resources = None, op = operator.or_):

        resources = self._resources_set(resources)

        return op(
            self.direction[self.a_b] & resources,
            self.direction[self.b_a] & resources,
        )


    def is_stimulation(self, direction = None, resources = None):
        """
        Checks if any (or for a specific *direction*) interaction is
        activation (positive interaction).

        :arg tuple direction:
            Optional, ``None`` by default. If specified, checks the
            :py:attr:`positive` attribute of that specific
            directionality. If not specified, checks both.

        :return:
            (*bool*) -- ``True`` if any interaction (or the specified
            *direction*) is activatory (positive).
        """

        return self._is_effect(
            sign = 'positive',
            direction = direction,
            resources = resources,
        )


    def is_inhibition(self, direction = None, resources = None):
        """
        Checks if any (or for a specific *direction*) interaction is
        inhibition (negative interaction).

        :arg tuple direction:
            Optional, ``None`` by default. If specified, checks the
            :py:attr:`negative` attribute of that specific
            directionality. If not specified, checks both.

        :return:
            (*bool*) -- ``True`` if any interaction (or the specified
            *direction*) is inhibitory (negative).
        """

        return self._is_effect(
            sign = 'negative',
            direction = direction,
            resources = resources,
        )


    def _is_effect(self, sign, direction = None, resources = None):

        _sign = getattr(self, sign)
        _resources = self._resources_set(resources)

        return (
            any(
                bool(
                    _evidences
                        if not _resources else
                    _evidences & _resources
                )
                for _direction, _evidences in iteritems(_sign)
                if not direction or direction == _direction
            )
        )


    def has_sign(self, direction = None, resources = None):
        """
        Checks whether the edge (or for a specific *direction*) has
        any signed information (about positive/negative interactions).

        :arg tuple direction:
            Optional, ``None`` by default. If specified, only the
            information of that direction is checked for sign.

        :return:
            (*bool*) -- ``True`` if there exist any information on the
              sign of the interaction, ``False`` otherwise.
        """

        return (
            self.is_stimulation(direction = direction, resources = resources)
                or
            self.is_inhibition(direction = direction, resources = resources)
        )


    def add_sign(
            self,
            direction,
            sign,
            resource = None,
            resource_name = None,
            interaction_type = 'PPI',
            data_model = None,
            **kwargs
        ):
        """
        Sets sign and source information on a given direction of the
        edge. Modifies the attributes :py:attr:`positive` and
        :py:attr:`positive_sources` or :py:attr:`negative` and
        :py:attr:`negative_sources` depending on the sign. Direction is
        also updated accordingly, which also modifies the attributes
        :py:attr:`dirs` and :py:attr:`sources`.

        :arg tuple direction:
            Pair of edge nodes specifying the direction from which the
            information is to be set/updated.
        :arg str sign:
            Specifies the type of interaction. Either ``'positive'`` or
            ``'negative'``.
        :arg set resource:
            Contains the name(s) of the source(s) from which the
            information was obtained.
        :arg **kwargs:
            Passed to ``pypath.resource.NetworkResource`` if ``resource``
            is not already a ``NetworkResource`` or ``Evidence``
            instance.
        """
        
        sign = self._effect_synonyms(sign)
        
        evidence = (
            resource
                if isinstance(resource, pypath_evidence.Evidence) else
            pypath_evidence.Evidence(
                resource = resource,
                references = references,
            )
                if isinstance(resource, pypath_resource.NetworkResource) else
            pypath_evidence.Evidence(
                resource = pypath_resource.NetworkResource(
                    name = resource_name,
                    interaction_type = interaction_type,
                    data_model = data_model,
                    **kwargs,
                )
            )
                if resource_name is not None else
            None
        )
        
        direction = self.direction_key(direction)
        
        if self._directed_key(direction) and evidence is not None:
            
            ev_attr = getattr(self, sign)
            ev_attr += evidence


    def get_sign(
            self,
            direction,
            sign = None,
            evidences = False,
            resources = False,
            resource_names = False,
            sources = False,
        ):
        """
        Retrieves the sign information of the edge in the given
        diretion. If specified in *sign*, only that sign's information
        will be retrieved. If specified in *sources*, the sources of
        that information will be retrieved instead.

        :arg tuple direction:
            Contains the pair of nodes specifying the directionality of
            the edge from which th information is to be retrieved.
        :arg str sign:
            Optional, ``None`` by default. Denotes whether to retrieve
            the ``'positive'`` or ``'negative'`` specific information.
        :arg bool resources:
            Optional, ``False`` by default. Specifies whether to return
            the resources instead of sign.

        :return:
            (*list*) -- If ``sign=None`` containing [bool] values
            denoting the presence of positive and negative sign on that
            direction, if ``sources=True`` the [set] of sources for each
            of them will be returned instead. If *sign* is specified,
            returns [bool] or [set] (if ``sources=True``) of that
            specific direction and sign.
        """

        sign = self._effect_synonyms(sign)
        
        answer_type_args = {
            'resources': resources,
            'evidences': evidences,
            'resource_names': resource_names,
            'sources': sources,
        }
        
        direction = self.direction_key(direction)
        
        if self._directed_key(direction):

            return (
                
                self._select_answer_type(
                    getattr(self, sign)[direction],
                    **answer_type_args
                )
                
                    if sign else
                
                [
                    self._select_answer_type(
                        self.positive[direction],
                        **answer_type_args
                    ),
                    self._select_answer_type(
                        self.negative[direction],
                        **answer_type_args
                    )
                ]
                
            )


    def source(
            self,
            undirected = False,
            resources = None,
            **kwargs
        ):
        """
        Returns the name(s) of the source node(s) for each existing
        direction on the interaction.

        :arg bool undirected:
            Optional, ``False`` by default.

        :returns:
            (*list*) -- Contains the name(s) for the source node(s).
            This means if the interaction is bidirectional, the list
            will contain both identifiers on the edge. If the
            interaction is undirected, an empty list will be returned.
        """

        return self._partner(
            source_target = 'source',
            undirected = undirected,
            resources = resources,
            **kwargs
        )


    # synonym: old name
    src = source


    def target(
            self,
            undirected = False,
            resources = None,
            **kwargs
        ):
        """
        Returns the name(s) of the target node(s) for each existing
        direction on the interaction.

        :arg bool undirected:
            Optional, ``False`` by default.

        :returns:
            (*list*) -- Contains the name(s) for the target node(s).
            This means if the interaction is bidirectional, the list
            will contain both identifiers on the edge. If the
            interaction is undirected, an empty list will be returned.
        """

        return self._partner(
            source_target = 'target',
            undirected = undirected,
            resources = resources,
            **kwargs
        )


    # synonym: old name
    tgt = target


    def _partner(
            self,
            source_target,
            undirected = False,
            resources = None,
            **kwargs
        ):

        resources = self._resources_set(resources)
        _slice = slice(0, 1) if source_target == 'source' else slice(1, 2)

        return tuple(itertools.chain(
            (
                _direction[_slice]
                    if _direction != 'undirected' else
                self.nodes
                    if undirected else
                ()
            )
            for _direction, _evidences in iteritems(self.direction)
            if (
                (
                    (
                        not resources and
                        not kwargs and
                        bool(_evidences)
                    ) or
                    (
                        any(
                            ev.match(
                                resource = res,
                                **kwargs
                            )
                            for res in resources or (None,)
                            for ev in _evidences
                        )
                    )
                )
            )
        ))


    def src_by_resource(self, resource):
        """
        Returns the name(s) of the source node(s) for each existing
        direction on the interaction for a specific *resource*.

        :arg str resource:
            Name of the resource according to which the information is to
            be retrieved.

        :return:
            (*list*) -- Contains the name(s) for the source node(s)
            according to the specified *resource*. This means if the
            interaction is bidirectional, the list will contain both
            identifiers on the edge. If the specified *source* is not
            found or invalid, an empty list will be returned.
        """

        return [
            _dir[0]
            for _dir, _evidences in iteritems(self.direction)
            if (
                _dir != 'undirected' and
                resource in _evidences
            )
        ]


    def tgt_by_resource(self, resource):
        """
        Returns the name(s) of the target node(s) for each existing
        direction on the interaction for a specific *resource*.

        :arg str resource:
            Name of the resource according to which the information is to
            be retrieved.

        :return:
            (*list*) -- Contains the name(s) for the target node(s)
            according to the specified *resource*. This means if the
            interaction is bidirectional, the list will contain both
            identifiers on the edge. If the specified *source* is not
            found or invalid, an empty list will be returned.
        """

        return [
            _dir[1]
            for _dir, _evidences in iteritems(self.direction)
            if (
                _dir != 'undirected' and
                resource in _evidences
            )
        ]


    def resources_a_b(
            self,
            resources = False,
            evidences = False,
            resource_names = False,
            sources = False,
        ):
        """
        Retrieves the list of resources for the :py:attr:`a_b`
        direction.

        :return:
            (*set*) -- Contains the names of the sources supporting the
            :py:attr:`a_b` directionality of the edge.
        """

        answer_type_args = {
            'resources': resources,
            'evidences': evidences,
            'resource_names': resource_names,
            'sources': sources,
        }

        return self._select_answer_type(
            self.direction[self.a_b],
            **answer_type_args
        )


    # synonym for old method name
    sources_straight = resources_a_b


    def resources_b_a(
            self,
            resources = False,
            evidences = False,
            resource_names = False,
            sources = False,
        ):
        """
        Retrieves the list of sources for the :py:attr:`b_a` direction.

        :return:
            (*set*) -- Contains the names of the sources supporting the
            :py:attr:`b_a` directionality of the edge.
        """

        answer_type_args = {
            'resources': resources,
            'evidences': evidences,
            'resource_names': resource_names,
            'sources': sources,
        }

        return self._select_answer_type(
            self.direction[self.b_a],
            **answer_type_args
        )


    # synonym for old method name
    sources_reverse = resources_b_a


    def resources_undirected(
            self,
            resources = False,
            evidences = False,
            resource_names = False,
            sources = False,
        ):
        """
        Retrieves the list of resources without directed information.

        :return:
            (*set*) -- Contains the names of the sources supporting the
            edge presence but without specific directionality
            information.
        """

        answer_type_args = {
            'resources': resources,
            'evidences': evidences,
            'resource_names': resource_names,
            'sources': sources,
        }

        return self._select_answer_type(
            self.direction['undirected'],
            **answer_type_args
        )


    sources_undirected = resources_undirected


    def positive_a_b(self):
        """
        Checks if the :py:attr:`a_b` directionality is a positive
        interaction.

        :return:
            (*bool*) -- ``True`` if there is supporting information on
            the :py:attr:`a_b` direction of the edge as activation.
            ``False`` otherwise.
        """

        return bool(self.positive[self.a_b])


    positive_straight = positive_a_b


    def positive_b_a(self):
        """
        Checks if the :py:attr:`b_a` directionality is a positive
        interaction.

        :return:
            (*bool*) -- ``True`` if there is supporting information on
            the :py:attr:`b_a` direction of the edge as activation.
            ``False`` otherwise.
        """

        return bool(self.positive[self.b_a])


    positive_reverse = positive_b_a


    def negative_a_b(self):
        """
        Checks if the :py:attr:`a_b` directionality is a negative
        interaction.

        :return:
            (*bool*) -- ``True`` if there is supporting information on
            the :py:attr:`a_b` direction of the edge as inhibition.
            ``False`` otherwise.
        """

        return bool(self.negative[self.a_b])


    negative_straight = negative_a_b


    def negative_b_a(self):
        """
        Checks if the :py:attr:`b_a` directionality is a negative
        interaction.

        :return:
            (*bool*) -- ``True`` if there is supporting information on
            the :py:attr:`b_a` direction of the edge as inhibition.
            ``False`` otherwise.
        """

        return bool(self.negative[self.b_a])


    negative_reverse = negative_b_a


    def negative_resources_a_b(self, **kwargs):
        """
        Retrieves the list of resources for the :py:attr:`a_b`
        direction and negative sign.

        :return:
            (*set*) -- Contains the names of the resources supporting the
            :py:attr:`a_b` directionality of the edge with a
            negative sign.
        """

        answer_type_args = {
            'resource_names': True
        }
        answer_type_args.update(kwargs)

        return self._select_answer_type(
            self.negative[self.a_b],
            **answer_type_args
        )


    def negative_resources_b_a(self, **kwargs):
        """
        Retrieves the list of resources for the :py:attr:`b_a`
        direction and negative sign.

        :return:
            (*set*) -- Contains the names of the resources supporting the
            :py:attr:`b_a` directionality of the edge with a
            negative sign.
        """
        
        answer_type_args = {
            'resource_names': True
        }
        answer_type_args.update(kwargs)

        return self._select_answer_type(
            self.negative[self.b_a],
            **answer_type_args
        )


    def positive_resources_a_b(self, **kwargs):
        """
        Retrieves the list of resources for the :py:attr:`a_b`
        direction and positive sign.

        :return:
            (*set*) -- Contains the names of the resources supporting the
            :py:attr:`a_b` directionality of the edge with a
            positive sign.
        """

        answer_type_args = {
            'resource_names': True
        }
        answer_type_args.update(kwargs)

        return self._select_answer_type(
            self.positive[self.a_b],
            **answer_type_args
        )


    def positive_resources_b_a(self, **kwargs):
        """
        Retrieves the list of resources for the :py:attr:`b_a`
        direction and positive sign.

        :return:
            (*set*) -- Contains the names of the resources supporting the
            :py:attr:`b_a` directionality of the edge with a
            positive sign.
        """

        answer_type_args = {
            'resource_names': True
        }
        answer_type_args.update(kwargs)

        return self._select_answer_type(
            self.positive[self.b_a],
            **answer_type_args
        )


    def majority_dir(
            self,
            only_interaction_type = None,
            only_primary = False,
            by_references = False,
            by_reference_resource_pairs = True,
        ):
        """
        Infers which is the major directionality of the edge by number
        of supporting sources.

        :return:
            (*tuple*) -- Contains the pair of nodes denoting the
            consensus directionality. If the number of sources on both
            directions is equal, ``None`` is returned. If there is no
            directionality information, ``'undirected'``` will be
            returned.
        """
        
        
        a_b = self.direction[self.a_b]
        b_a = self.direction[self.b_a]
        
        if not a_b and not b_a:
            
            return 'undirected'
        
        method = (
            'count_references'
                if by_references else
            'count_curation_effort'
                if by_reference_resource_pairs else
            'count_resources'
        )
        
        n_a_b = getattr(a_b, method)(
            interaction_type = only_interaction_type,
            via = False if only_primary else None,
        )
        n_b_a = getattr(b_a, method)(
            interaction_type = only_interaction_type,
            via = False if only_primary else None,
        )
        
        return (
            'undirected'
                if n_a_b == 0 and n_b_a == 0 else
            None
                if n_a_b == n_b_a else
            self.a_b
                if n_a_b > n_b_a else
            self.b_a
        )


    def majority_sign(
            self,
            only_interaction_type = None,
            only_primary = False,
            by_references = False,
            by_reference_resource_pairs = True,
        ):
        """
        Infers which is the major sign (activation/inhibition) of the
        edge by number of supporting sources on both directions.

        :return:
            (*dict*) -- Keys are the node tuples on both directions
            (:py:attr:`straight`/:py:attr:`reverse`) and values can be
            either ``None`` if that direction has no sign information or
            a list of two [bool] elements corresponding to majority of
            positive and majority of negative support. In case both
            elements of the list are ``True``, this means the number of
            supporting sources for both signs in that direction is
            equal.
        """
        
        result = {}
        
        method = (
            'count_references'
                if by_references else
            'count_curation_effort'
                if by_reference_resource_pairs else
            'count_resources'
        )
        
        for _dir in (self.a_b, self.b_a):
            
            n_pos = getattr(self.positive[_dir], method)(
                interaction_type = only_interaction_type,
                via = False if only_primary else None,
            )
            n_neg = getattr(self.negative[_dir], method)(
                interaction_type = only_interaction_type,
                via = False if only_primary else None,
            )
            
            result[_dir] = [
                0 < n_pos >= n_neg,
                0 < n_neg >= n_pos,
            ]
        
        return result


    def consensus(
            self,
            only_interaction_type = None,
            only_primary = False,
            by_references = False,
            by_reference_resource_pairs = True,
        ):
        """
        Infers the consensus edge(s) according to the number of
        supporting sources. This includes direction and sign.

        :return:
            (*list*) -- Contains the consensus edge(s) along with the
            consensus sign. If there is no major directionality, both
            are returned. The structure is as follows:
            ``['<source>', '<target>', '<(un)directed>', '<sign>']``
        """

        result = []
        
        _dir = self.majority_dir(
            only_interaction_type = only_interaction_type,
            only_primary = only_primary,
            by_references = by_references,
            by_reference_resource_pairs = by_reference_resource_pairs,
        )
        _effect = self.majority_sign(
            only_interaction_type = only_interaction_type,
            only_primary = only_primary,
            by_references = by_references,
            by_reference_resource_pairs = by_reference_resource_pairs,
        )

        if _dir == 'undirected':
            
            result.append([
                self.a_b[0],
                self.a_b[1],
                'undirected',
                'unknown',
            ])

        else:
            
            dirs = (self.a_b, self.b_a) if _dir is None else (_dir,)

            for d in dirs:

                if _effect[d] is not None:
                    
                    # index #0 is positive
                    if _effect[d][0]:
                        
                        result.append([
                            d[0],
                            d[1],
                            'directed',
                            'positive',
                        ])
                    
                    # can not be elif bc of the case of equal weight of
                    # evidences for both positive and negative
                    if _effect[d][1]:
                        
                        result.append([
                            d[0],
                            d[1],
                            'directed',
                            'negative',
                        ])
                
                # directed with unknown effect
                else:
                    
                    result.append([
                        d[0],
                        d[1],
                        'directed',
                        'unknown',
                    ])

        return result


    consensus_edges = consensus


    def merge(self, other):
        """
        Merges current Interaction with another (if and only if they are the
        same class and contain the same nodes). Updates the attributes
        :py:attr:`direction`, :py:attr:`positive` and :py:attr:`negative`.

        :arg pypath.interaction.Interaction other:
            The new Interaction object to be merged with the current one.
        """
        
        
        if not self._check_nodes_key(other.nodes):
            
            _log(
                'Attempting to merge Interaction instances with different '
                'interacting partners.'
            )
            return
        
        self.evidences += other.evidences
        
        for attr, _dir in itertools.product(
            ('direction', 'positive', 'negative'),
            (self.a_b, self.b_a, 'undirected')
        ):
            
            if attr != 'direction' and _dir == 'undirected':
                
                continue
            
            getattr(self, attr)[_dir] += getattr(other, attr)[_dir]


    def translate(self, ids, new_attrs = None):
        """
        Translates the node names/identifiers according to the
        dictionary *ids*. Also is able to change attributes like `id_type`,
        `taxon` and `entity_type`.

        :arg dict ids:
            Dictionary containing (at least) the current names of the
            nodes as keys and their translation as values.
        :arg dict new_attrs:
            Dictionary with new IDs as keys and their dicts of their new
            attributes as values. For any attribute not provided here
            the attributes from the original instance will be used.
            E.g. you can provide `{'1956': {'id_type': 'entrez'}}' if the
            new ID type for protein EGFR is Entrez Gene ID.

        :return:
            (*pypath.main.Direction*) -- The copy of current edge object
            with translated node names.
        """

        new_a = ids[self.nodes[0]]
        new_b = ids[self.nodes[1]]
        new_ids = {'a': new_a, 'b': new_b}
        to_old = common.swap_dict_simple(ids)
        
        all_new_attrs = dict(
            (
                '%s_%s' % (attr, label),
                new_attrs[new_ids[label]][attr]
                    if (
                        new_ids[label] in new_attrs and
                        attr in new_attrs[new_ids[label]]
                    ) else
                getattr(self, '%s_%s' % (attr, label))
            )
            for attr in ('id_type', 'entity_type', 'taxon')
            for label in ('a', 'b')
        )
        
        new = Interaction(
            id_a = new_a,
            id_b = new_b,
            **all_new_attrs
        )
        
        new.evidences += self.evidences
        
        for (old_dir, new_dir), attr in itertools.product(
            zip(
                (
                    (to_old[new.id_a], to_old[new.id_b]),
                    (to_old[new.id_b], to_old[new.id_a]),
                    'undirected'
                ),
                (
                    new.a_b,
                    new.b_a,
                    'undirected',
                ),
            ),
            ('direction', 'positive', 'negative'),
        ):
            
            if _dir == 'undirected' and attr != 'direction':
                
                continue
            
            
            getattr(self, attr)[new_dir] += getattr(self, attr)[old_dir]
        
        return new
    
    
    def get_evidences(
            self,
            direction = None,
            effect = None,
            resources = None,
            data_model = None,
            interaction_type = None,
            via = None,
            references = None,
        ):
        
        evidences = (
            
            # any signed
            sum(itertools.chain(
                self.positive.values(),
                self.negative.values(),
            ))
                
                if effect == True else
                
            # only positive
            (
                self.positive[direction]
                    if direction in self.positive else
                sum(self.positive.values())
            )
                
                if effect == 'positive' else
                
            # only negative
            (
                self.positive[direction]
                    if direction in self.positive else
                sum(self.positive.values())
            )
                
                if effect == 'negative' else
                
            # any directed
            sum(self.direction[_dir] for _dir in self.which_dirs())
                
                if direction == True else
                
            # one specific direction
            self.direction[direction]
                
                if direction in self.direction else
                
            # all evidences (default)
            self.evidences
            
        )
        
        return (
            pypath_evidence.Evidences(
                evidences.filter(
                    resource = resources,
                    interaction_type = interaction_type,
                    via = via,
                    data_model = data_model,
                    references = references,
                )
            )
        )
    
    
    def get_references(
            self,
            direction = None,
            effect = None,
            resources = None,
            data_model = None,
            interaction_type = None,
            via = None,
        ):
            
            return self._get('references', **locals())
    
    
    def get_resources(
            self,
            direction = None,
            effect = None,
            resources = None,
            data_model = None,
            interaction_type = None,
            via = None,
        ):
            
            return self._get('resources', **locals())
    
    
    def get_resource_names(
            self,
            direction = None,
            effect = None,
            resources = None,
            data_model = None,
            interaction_type = None,
            via = None,
        ):
            
            return self._get('resource_names', **locals())
    
    
    def get_curation_effort(
            self,
            direction = None,
            effect = None,
            resources = None,
            data_model = None,
            interaction_type = None,
            via = None,
        ):
            
            return self._get('curation_effort', **locals())
    
    
    def get_entities(self):
        
        return {self.a, self.b}
    
    
    def get_identifiers(self):
        
        return {self.a.identifier, self.b.identifier}
    
    
    def get_labels(self):
        
        return {self.a.label, self.b.label}
    
    
    def get_interactions(
            self,
            directed = False,
        ):
        
        
    
    
    @staticmethod
    def _get(method, *args, **kwargs):
        
        self = kwargs.pop('self')
        
        return getattr(
            self.get_evidences(
                *args,
                **kwargs
            ),
            'get_%s' % method,
        )()
    
    
    @staticmethod
    def _count(method):
        
        @functools.wraps(method)
        def count_method(*args, **kwargs):
            
            return len(method(*args, **kwargs))
        
        return count_method
    
    
    count_references = _count.__func__(get_references)
    count_resources = _count.__func__(get_resources)
    count_curation_effort = _count.__func__(get_curation_effort)
    count_entities = _count.__func__(get_entities)
    count_resource_names = _count.__func__(get_resource_names)

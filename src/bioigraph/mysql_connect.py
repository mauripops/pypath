#!/usr/bin/env python2
# -*- coding: utf-8 -*-

#
#  This file is part of the `bioigraph` python module
#
#  Copyright (c) 2014-2015 - EMBL-EBI
#
#  File author(s): Dénes Türei (denes@ebi.ac.uk)
#
#  Distributed under the GNU GPLv3 License.
#  See accompanying file LICENSE.txt or copy at
#      http://www.gnu.org/licenses/gpl-3.0.html
#
#  Website: http://www.ebi.ac.uk/~denes
#

import os
import sys
import ConfigParser
import pymysql as MySQLdb
import pymysql.cursors as cursors

import common

class MysqlConnect(object):
    
    def __init__(self,config=None,log=None):
        '''
        config is the name of a connection config file
        '''
        self.log = log
        self.conf_file = config if config is not None \
            else os.path.join(common.ROOT,'mysql_config','defaults.mysql')
        self.conf_reader = ConfigParser.RawConfigParser()
        self.conf_reader.read(self.conf_file)
        self.configs = self.conf_reader.sections()
        self.access = {}
        self.read_configs()
    
    def read_configs(self):
        for name in self.configs:
            self.read_config(name)
    
    def read_config(self,name):
        try:
            self.access[name] = {
                            'host': self.conf_reader.get(name,'host'),
                            'user': self.conf_reader.get(name,'user'),
                            'password': self.conf_reader.get(name,'password'),
                            'db': self.conf_reader.get(name,'database')
                        }
            if self.conf_reader.has_option(name,'port'):
                self.access[name]['port'] = int(self.conf_reader.get(name,'port'))
            else:
                self.access[name]['port'] = 3306
        except:
            self.access[name] = None
            error = 'Could not read MySQL settings from file %s in section %s' % \
                (self.conf_file,name)
            if self.log is not None:
                self.log.msq(2, error, 'ERROR')
            else:
                common.console(error)
    
    def get_connection(self,name):
        if self.access[name] is None:
            self.read_config(name)
        if self.access[name] is None:
            self.access[name] = None
            error = 'Configuration missing to access MySQL for %s' % (name)
            if self.log is not None:
                self.log.msq(2, error, 'ERROR')
            else:
                common.console(error)
        else:
            try:
                con = MySQLdb.connect(
                    host = self.access[name]['host'],
                    user = self.access[name]['user'],
                    port = self.access[name]['port'],
                    passwd = self.access[name]['password'],
                    db = self.access[name]['db'],
                    cursorclass=cursors.DictCursor
                )
                return con
            except:
                error = 'Failed to connect MySQL `%s\'.' % name
                if self.log is not None:
                    self.log.msg(2, error, 'ERROR')
                else:
                    common.console(error)
                return None

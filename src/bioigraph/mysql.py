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

import sys
import codecs
import pymysql as MySQLdb
import pymysql.cursors as cursors

import mysql_connect

class MysqlRunner(object):
    
    def __init__(self,param,log=None,silent=False):
        '''
        param is either a tuple of the name of mysql access config file,
        and the title of the config section in it, or
        or a dict with the config itself
        '''
        self.con = None
        self.log = log
        self.param = param
        self.silent = silent
        self.reconnect()
    
    def get_connection(self):
        return MySQLdb.connect(
            host = self.param['host'],
            user = self.param['user'],
            port = self.param['port'],
            passwd = self.param['password'],
            db = self.param['db'],
            cursorclass = cursors.DictCursor
            )
    
    def connekt(self):
        if type(self.param) is tuple:
            self.access = mysql_connect.MysqlConnect(self.param[0], log=self.log)
            self.new_con = self.access.get_connection(self.param[1])
        else:
            if 'port' not in self.param:
                self.param['port'] = 3306
            self.new_con = self.get_connection()
    
    def reconnect(self):
        self.connekt()
        if self.new_con is not None:
            self.con = self.new_con
    
    def run_query(self,query,silent=None):
        silent = self.silent if silent is None else silent
        if not silent:
            sys.stdout.write('\t:: Waiting for MySQL...')
            sys.stdout.flush()
        with open('mysql.log', 'w') as f:
            f.write(query+'\n')
        if self.con is not None:
            try:
                cur = self.con.cursor()
                cur.execute(query)
                self.result = cur.fetchall()
                cur.close()
                if not silent:
                    sys.stdout.write(' Done.\n')
            except MySQLdb.Error, e:
                emsg = 'MySQL error occured. See `mysql.error` for details.'
                self.send_error(emsg)
                out = "MySQL Error [%d]: %s\n\n" % (e.args[0], e.args[1])
                out += "Failed to execute query:\n\n"
                out += query
                with codecs.open('mysql.error','w') as f:
                    f.write(out)
                self.result = []
        else:
            emsg = 'No connection to MySQL'
            self.send_error(emsg)
    
    def print_status(self):
        pid = self.con.thread_id()
        self.connekt()
        con2 = self.new_con
        q = '''SELECT STATE,TIME 
            FROM information_schema.processlist 
            WHERE Id = %u;''' % pid
        cur = con2.cursor()
        try:
            cur.execute(q)
            res = cur.fetchone()
            status = res['STATE'] if len(res['STATE'].strip()) > 0 else 'Undefined state'
            sys.stdout.write('\r'+' '*90)
            sys.stdout.write('\r\t:: MySQL: %s, running for %u seconds.' % \
                (status,res['TIME']))
            sys.stdout.flush()
        except:
            sys.stdout.write('\r'+' '*90)
            sys.stdout.write('\r\t:: MySQL: finished.')
            sys.stdout.flush()
        cur.close()
        con2.close()
    
    def send_error(self,error_message):
        if self.log is not None:
            self.log.msg(1,error_message,'ERROR')
        else:
            sys.stdout.write('\n\t:: '+error_message+'\n\n')
            sys.stdout.flush()
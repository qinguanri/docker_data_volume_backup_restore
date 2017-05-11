#!/usr/bin/python
# -*- coding: utf-8 -*-

import logging
import logging.handlers
import time
import os
import argparse
import subprocess
import traceback
import json
import codecs
import re
import sys
from distutils.spawn import find_executable


LOG_FILE = '/var/log/chronus.log'
LOGGING_FMT = '%(module)s[%(process)d]:%(levelname)s:%(message)s'

# Record backup meta data at a json file.
BACKUP_JSON_FILE = '/var/local/backuplist.json'


def do_cmd(cmd, **kwargs):
    kwargs_ = {
        'stdout': subprocess.PIPE,
        'stderr': subprocess.PIPE,
        'universal_newlines': True
    }
    kwargs_.update(kwargs)
    p = subprocess.Popen(cmd, **kwargs_)
    return p.communicate()


def dump_backup_list(backuplist, filename):
    with codecs.open(filename, 'w+', 'utf8') as file:
        file.write(json.dumps(backuplist, ensure_ascii=False))
    return True


def load_backup_list(filename):
    try:
        with open(filename) as json_data:
            return json.load(json_data)
    except:
        return []


def is_volume_active(volume):
    res, err = do_cmd(['lvdisplay', volume])
    return re.search('LV Status.+available', res)


def stop_service():
    # do_cmd(['systemctl', 'stop', 'docker'])
    pass


def start_service():
    # do_cmd(['systemctl', 'start', 'docker'])
    pass


def compress_file(dest, src):
    if not os.path.exists(os.path.dirname(dest)):
        os.makedirs(os.path.dirname(dest))
    try:
        cmd = ['tar', '-zpcf', dest, '-C', src, './']
        if os.path.isfile(find_executable('pigz')):
            cmd = ['tar', '-I', 'pigz', '-cpf', dest, '-C', src, './']
        do_cmd(cmd)
        return dest
    except Exception, e:
        os.remove(dest)
        raise Exception('tar failed, dest: ' + dest + ' err:' + str(e))


def uncompress_file(dest, src):
    if not os.path.isfile(src):
        raise Exception('there is no such file: ', src)
    if not os.path.isabs(dest):
        raise Exception('the path is invalid: ', dest)
    if not os.path.isdir(dest):
        os.makedirs(dest)
    do_cmd(['tar', 'xzf', src, '-C', dest])
    return dest


def insert_backup(backup):
    backuplist = load_backup_list(BACKUP_JSON_FILE)
    backuplist.append(backup)
    dump_backup_list(backuplist, BACKUP_JSON_FILE)
    return backuplist


def remove_backup(backup):
    backuplist = load_backup_list(BACKUP_JSON_FILE)
    for item in backuplist[:]:
        if item['filename'] == backup['filename']:
            os.remove(backup['filename'])
            backuplist.remove(item)
    dump_backup_list(backuplist, BACKUP_JSON_FILE)
    return backuplist


def get_backup_list():
    backuplist = load_backup_list(BACKUP_JSON_FILE)
    for backup in backuplist[:]:
        if not os.path.isfile(backup['filename']):
            backuplist.remove(backup)
    dump_backup_list(backuplist, BACKUP_JSON_FILE)
    return backuplist


def create_snapshot(snapname, lv_path):
    do_cmd(['lvcreate', '-L100M', '-s', '-n', snapname, lv_path])
    vg_name = lv_path.split('/')[2]
    snapshot_lv_path = '/dev/{}/{}'.format(vg_name, snapname)
    if not is_volume_active(snapshot_lv_path):
        raise Exception('create snapshot failed')
    else:
        return snapshot_lv_path


def remove_snapshot(lv_path):
    return do_cmd(['lvremove', '-f', lv_path])


def mount_volume(dir, lv_path):
    if not os.path.exists(dir):
        os.makedirs(dir)
    cmd = ['mount', '-t', 'xfs', lv_path, dir, '-onouuid,ro']
    return do_cmd(cmd)


def umount_volume(lv_path):
    return do_cmd(['umount', lv_path])


def cmd_backup_create(args):
    snap_lv_path = create_snapshot('datasnapshot', args.lv_path)

    mount_dir = '/mnt/snapshot'
    mount_volume(mount_dir, snap_lv_path)

    cur_time = time.strftime("%Y%m%d%H%M%S")
    filename = '{}/{}.tgz'.format(args.dest, cur_time)
    compress_file(filename, mount_dir)
    umount_volume(snap_lv_path)
    remove_snapshot(snap_lv_path)

    res = insert_backup({
        'filename': filename,
        'create_at': cur_time,
        'bytes': os.path.getsize(filename),
        'version': '9.5',
        'remark': "",
        'operator': ""
    })
    print(json.dumps(res, sort_keys=True))


def cmd_backup_delete(args):
    res = remove_backup({'filename': args.path})
    print(json.dumps(res, sort_keys=True))


def cmd_backup_list(args):
    print(json.dumps(get_backup_list(), sort_keys=True))


def cmd_restore(args):
    stop_service()
    uncompress_file(args.dest, args.backupfile)
    start_service()
    print(json.dumps({'code': 200, 'msg': 'success'}))


def main():
    parser = argparse.ArgumentParser(
        description='Process backup or restore task.')
    subparsers = parser.add_subparsers(
        help='sub-command help')

    # Subcommand `backup`
    parser_backup = subparsers.add_parser(
        'backup',
        help='create backup or list backup files')
    subparsers_backup = parser_backup.add_subparsers(
        help='backup sub-command help')

    #  Subcommand `backup create`
    parser_backup_create = subparsers_backup.add_parser(
        'create',
        help='create a backupfile')
    parser_backup_create.add_argument(
        'lv_path',
        help='specify the logical volume path which needs to backup')
    parser_backup_create.add_argument(
        '--dest',
        default='/backup',
        help='the directory to save the backup file')
    parser_backup_create.set_defaults(func=cmd_backup_create)

    # Subcommand `backup delete`
    parser_backup_delete = subparsers_backup.add_parser(
        'delete',
        help='delete a backup file')
    parser_backup_delete.add_argument(
        'path',
        help='path of the backup file')
    parser_backup_delete.set_defaults(func=cmd_backup_delete)

    # Subcommand `backup list`
    parser_backup_list = subparsers_backup.add_parser(
        'list',
        help='list the information of backup files')
    parser_backup_list.set_defaults(func=cmd_backup_list)

    # Subcommand `restore`
    parser_restore = subparsers.add_parser(
        'restore',
        help='restore with a backupfile')
    parser_restore.add_argument(
        'backupfile',
        help='specify a backup file to restore')
    parser_restore.add_argument(
        '--dest',
        default='/data',
        help='specify the directory to extract backupfile')
    parser_restore.set_defaults(func=cmd_restore)

    # Call appropriate handler
    args = parser.parse_args()
    if hasattr(args, 'func'):
        args.func(args)


if __name__ == '__main__':
    try:
        main()
    except Exception, err:
        logging.basicConfig(format=LOGGING_FMT)
        logging.critical('\n%s', traceback.format_exc())
        print err
        sys.exit(1)

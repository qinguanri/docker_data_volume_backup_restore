#!/usr/bin/python
# -*- coding: utf-8 -*-

import logging
import logging.handlers
import time
import os
import argparse
import subprocess
import traceback
import hashlib
import json
import codecs
import re
import sys
from distutils.spawn import find_executable


LOG_FILE = '/var/log/chronus.log'
LOGGING_FMT = '%(module)s[%(process)d]:%(levelname)s:%(message)s'

# Record backup meta data at a json file.
BACKUP_JSON_FILE = '/var/local/backuplist.json'
HISTORY_JSON_FILE = '/var/local/backuphistory.json'
BACKUP_META_FILENAME = '.backupmetadata'


def do_cmd(cmd, **kwargs):
    kwargs_ = {
        'stdout': subprocess.PIPE,
        'stderr': subprocess.PIPE,
        'universal_newlines': True
    }
    kwargs_.update(kwargs)
    p = subprocess.Popen(cmd, **kwargs_)
    return p.communicate()


def get_pg_version(dir):
    res, _ = do_cmd(['find', dir, '-name', 'PG_VERSION'])
    filename = res.split('\n')[0]
    if os.path.isfile(filename):
        with open(filename, 'r') as file:
            pg_version = file.read().strip()
            return pg_version
    else:
        return ""


def get_meta_from_backupfile(filename):
    if not os.path.isfile(filename) or not re.search('.+\.tgz', filename):
        return None
    do_cmd(['tar', 'xzf', filename, '-C', '/tmp', './' + BACKUP_META_FILENAME])
    metadata = read_data('/tmp/' + BACKUP_META_FILENAME)
    if not metadata or metadata == []:
        metadata = {
            'create_at': time.strftime("%Y%m%d%H%M%S"),
            'version': 'unknown',
            'remark': 'unknown',
            'operator': '',
        }
    if os.path.isfile('/tmp/' + BACKUP_META_FILENAME):
        os.remove('/tmp/' + BACKUP_META_FILENAME)
    return metadata


def md5_checksum(filename, block_size=64 * 1024):
    md5 = hashlib.md5()
    with open(filename, 'rb') as f:
        while True:
            data = f.read(block_size)
            if not data:
                break
            md5.update(data)
    return md5.hexdigest()


def write_data(data, filename):
    with codecs.open(filename, 'w+', 'utf8') as file:
        file.write(json.dumps(data, ensure_ascii=False))
    return True


def read_data(filename):
    try:
        with open(filename) as json_data:
            return json.load(json_data)
    except:
        return []


def dump_backup_list(backuplist, filename):
    return write_data(backuplist, filename)


def load_backup_list(filename):
    backuplist = read_data(filename)
    return unique_backup_list(backuplist)


def dump_history(history, filename):
    history = sorted(history, key=lambda item: item['timestamp'])
    return write_data(history[-100:], filename)


def load_history(filename):
    return read_data(filename)


def is_snapshot_active(volume):
    res, err = do_cmd(['lvdisplay', volume])
    return re.search('LV snapshot status.+active', res)


def is_lv_path(path):
    res, _ = do_cmd(['lvdisplay', path])
    return re.search('LV Status.+available', res)


def is_dir_path(path):
    return os.path.isdir(path)


def stop_service():
    # TODO: stop your services below
    do_cmd(['docker', 'stop', 'main'])
    do_cmd(['docker', 'stop', 'pg'])
    do_cmd(['docker', 'stop', 'redis'])
    do_cmd(['docker', 'stop', 'beanstalkd'])


def start_service():
    # TODO: start your services below
    do_cmd(['docker', 'start', 'beanstalkd'])
    do_cmd(['docker', 'start', 'redis'])
    do_cmd(['docker', 'start', 'pg'])
    do_cmd(['docker', 'start', 'main'])


def compress_file(dest, src, extendinfo):
    if not os.path.isabs(src):
        raise Exception('there is no such directory:', src)
    if not os.path.exists(os.path.dirname(dest)):
        os.makedirs(os.path.dirname(dest))
    try:
        # add a new file into tgz to recored meta data.
        write_data(extendinfo, src + "/" + BACKUP_META_FILENAME)
        cmd = ['tar', '-zpcf', dest, '-C', src, './']
        # use pigz to compress file with multi cpu.
        if os.path.isfile(find_executable('pigz') or ''):
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


def unique_backup_list(backuplist):
    md5list = []
    result = []
    for backup in backuplist:
        if backup['md5'] not in md5list:
            result.append(backup)
            md5list.append(backup['md5'])
    return result


def get_backup_list(dir):
    # check directory valid
    if dir and not os.path.exists(dir):
        return []

    backuplist = load_backup_list(BACKUP_JSON_FILE)
    for backup in backuplist[:]:
        # the file has been deleted
        if not os.path.isfile(backup['filename']):
            backuplist.remove(backup)
            continue
        # the file is not in the target directory
        if dir and os.path.dirname(backup['filename']) != dir:
            backuplist.remove(backup)

    # return all directory's backup files
    if not dir:
        return unique_backup_list(backuplist)

    # append the backupfile which has not been recorded in json file.
    filelist = [dir + '/' + file for file in os.listdir(dir)]
    backuppathlist = [backup['filename'] for backup in backuplist]
    for filename in filelist:
        if not os.path.isfile(filename):
            continue
        if filename in backuppathlist:
            continue
        meta = get_meta_from_backupfile(filename)
        if not meta:
            continue
        backup = {
            'filename': filename,
            'create_at': meta['create_at'],
            'version': meta['version'],
            'remark': meta['remark'],
            'operator': meta['operator'],
            'bytes': os.path.getsize(filename),
            'md5': md5_checksum(filename)
        }
        insert_backup(backup)
        backuplist.append(backup)
    return unique_backup_list(backuplist)


def get_backup_history():
    history = load_history(HISTORY_JSON_FILE)
    for item in history[:]:
        if item['cmd'] != 'cmd_backup_create':
            history.remove(item)
    return history


def create_snapshot(snapname, lv_path):
    do_cmd(['lvcreate', '-L2G', '-s', '-n', snapname, lv_path])
    vg_name = lv_path.split('/')[2]
    snapshot_lv_path = '/dev/{}/{}'.format(vg_name, snapname)
    if not is_snapshot_active(snapshot_lv_path):
        remove_snapshot(snapshot_lv_path)
        raise Exception('create snapshot failed.')
    else:
        return snapshot_lv_path


def log(func):
    def wrapper(*args, **kw):
        res = {
            'timestamp': time.strftime("%Y%m%d%H%M%S"),
            'cmd': func.__name__,
        }
        error = None
        try:
            msg = func(*args, **kw)
            res['code'] = 200
            res['msg'] = str(msg)
        except Exception, e:
            res['code'] = 500
            res['msg'] = str(e)
            error = e
        finally:
            history = load_history(HISTORY_JSON_FILE)
            history.append(res)
            dump_history(history, HISTORY_JSON_FILE)
            if error:
                raise Exception(error)

        return func
    return wrapper


def remove_snapshot(lv_path):
    return do_cmd(['lvremove', '-f', lv_path])


def mount_volume(dir, lv_path):
    if not os.path.exists(dir):
        os.makedirs(dir)
    cmd = ['mount', '-t', 'xfs', lv_path, dir, '-onouuid,ro']
    return do_cmd(cmd)


def umount_volume(lv_path):
    return do_cmd(['umount', lv_path])


def backup_offline(args):
    stop_service()
    cur_time = time.strftime("%Y%m%d%H%M%S")
    pg_version = get_pg_version(args.src)
    filename = '{}/{}.tgz'.format(args.dest, cur_time)
    extend_info = {
        'filename': filename,
        'create_at': cur_time,
        'version': pg_version,
        'remark': args.remark or "created offline",
        'operator': ""
    }

    compress_file(filename, args.src, extend_info)
    start_service()
    backupfile = extend_info
    backupfile['bytes'] = os.path.getsize(filename)
    backupfile['md5'] = md5_checksum(filename)

    return backupfile


def backup_online(args):
    snap_lv_path = create_snapshot('datasnapshot', args.src)
    mount_dir = '/mnt/snapshot'
    mount_volume(mount_dir, snap_lv_path)

    cur_time = time.strftime("%Y%m%d%H%M%S")
    pg_version = get_pg_version(mount_dir)
    filename = '{}/{}.tgz'.format(args.dest, cur_time)
    extend_info = {
        'filename': filename,
        'create_at': cur_time,
        'version': pg_version,
        'remark': args.remark or "created offline",
        'operator': ""
    }

    compress_file(filename, mount_dir, extend_info)
    umount_volume(snap_lv_path)
    remove_snapshot(snap_lv_path)

    backupfile = extend_info
    backupfile['bytes'] = os.path.getsize(filename)
    backupfile['md5'] = md5_checksum(filename)
    return backupfile


@log
def cmd_backup_create(args):
    backup = {}
    if is_dir_path(args.src):
        backup = backup_offline(args)
    elif is_lv_path(args.src):
        backup = backup_online(args)
    else:
        raise Exception('unexception argument src: ' + str(args.src))

    insert_backup(backup)
    print(json.dumps(backup, sort_keys=True))
    return json.dumps(backup, sort_keys=True)


def cmd_backup_delete(args):
    res = remove_backup({'filename': args.path})
    print(json.dumps(res, sort_keys=True))


def cmd_backup_list(args):
    print(json.dumps(get_backup_list(args.dir), sort_keys=True))


def cmd_backup_history(args):
    history = get_backup_history()
    if args.count <= 0:
        args.count = 1
    history = sorted(history, key=lambda item: item['timestamp'], reverse=True)
    print(json.dumps(history[:args.count], sort_keys=True))


def cmd_restore(args):
    stop_service()
    uncompress_file(args.dest, args.backupfile)
    start_service()
    print(json.dumps({'code': 200, 'msg': 'success'}))


def main():
    parser = argparse.ArgumentParser(
        description='Process backup or restore task.')
    parser.add_argument(
        '-v',
        '--version',
        action='version',
        version="${version_info}",    # jenkins will auto set it
        help='Show program version info and exit.')

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
        'src',
        help='specify the source path, '
        'it should be logical volume path or directory path.')
    parser_backup_create.add_argument(
        '--dest',
        default='/backup',
        help='the directory to save the backup file')
    parser_backup_create.add_argument(
        '--remark',
        default=None,
        help='the remark content')
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
    parser_backup_list.add_argument(
        '--dir',
        default=None,
        help='specify the directory')
    parser_backup_list.set_defaults(func=cmd_backup_list)

    # Subcommand `backup history`
    parser_backup_history = subparsers_backup.add_parser(
        'history',
        help='return the history results of backup commmand')
    parser_backup_history.add_argument(
        '--count',
        default=1,
        type=int,
        help='Specify the number of latest history results to be listed')

    parser_backup_history.set_defaults(func=cmd_backup_history)

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

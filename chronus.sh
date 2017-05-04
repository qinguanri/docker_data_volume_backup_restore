#!/bin/bash

VERSION="1.0.0.0"

LOG=/var/log/chronus.log                    # 记录日志
WORK_DIR=$(cd `dirname $0`; pwd)            # 当前skyha.sh文件所在绝对路径
BACKUP_LIST=/usr/local/bin/.backuplist.csv


log_info()  {
  _log "INFO" "$1"
}

log_warn()  { 
  _log "WARN" "$1"
}

log_error() { 
  _log "ERROR" "$1" 
}

_log() { 
  echo "[$(date +'%Y-%m-%dT%H:%M:%S%z')]: $@" >&2
  echo "[$(date +'%Y-%m-%dT%H:%M:%S%z')]: $@" >> ${LOG}
}

usage() {

}


encode() {

}


decode() {

}


# create_backup <original_volume> <backup_target>
create_backup() {
  original_volume=$1
  backup_target=$2

  snapshot_name=volsnapshot
  snapshot_volume=$(cat ${original_volume} | \
                    awk -F '/' '{print $NF/${snapshot_name}}')

  lvcreate -L10G -s -n ${snapshot_name} ${original_volume}
  mount_dir=/mnt/snapshot
  mkdir -p ${mount_dir} && mount ${snapshot_volume} ${mount_dir} -onouuid,ro
  encode ${snapshot_volume} ${backup_target}
  umount ${snapshot_volume}
  lvremove ${snapshot_volume}

  # -------------------------------------------------------------------
  # FILENAME,SIZE,CREATE_AT,VERSION,REMARK,OPERATOR,
  # -------------------------------------------------------------------
  filename=${backup_target}
  size=$(ls -l ${filename})
  create_at=$(date +%Y%m%d%H%M%S)
  ver=${VERSION}
  remark=""
  operator=""
  echo "${filename},${size},${create_at},${ver},${remark},${operator}" 
        >> ${BACKUP_LIST}

  log_info "[+] create backup succeed."
}


delete_backup() {

}


list_backup() {

}


inspect_backup() {

}


show_version() {
  echo "version: $VERSION"
}


# backup create <snapshot_volume> <dest>
cmd_backup() {
  cmd=$3
  case "${cmd}" in
    create) create_backup ;; 
    delete) delete_backup ;;  
    *) log_error "Unexpected command '${cmd}'" ;; 
  esac
}


cmd_restore() {
  cmd=$3
  case "${cmd}" in
    create) 
      ##
      ;; 
    *) 
      log_error "Unexpected command '${cmd}'"
      ;;
  esac
}

case "$1" in
  backup)                  cmd_backup $@;;
  restore)                 cmd_restore $@;;
  version|-v|--version)    show_version;;
  help|usage|-h|--help)    usage;;
  *)                       usage;;
esac


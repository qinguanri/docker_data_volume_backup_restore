# docker_data_volume_backup_restore
scripts to backup and restore docker volumes.

## commands:

* list
* cleanup
* backup
* restore

## usage

```shell
usage() {
    echo "
Scripts used to backup or restore a container's data. version: $VERSION

usage:

sky <command> [options]

the most commonly commands and options are:

list                 
    list all backup files at current container.
            
cleanup [-a|-i index|-f file]           
    clean up backup files at current container. clean up all by default.
    -a          : cleanup all backup files. 
    -i index    : cleanup a backup file specify by index. e.g: -i 2
    -f file     : cleanup a backup file specify by absolut file path. 
                  e.g: -f /backup/container_redis/20161225000000.tar

backup [-f file]            
    create a backup files at current container. 
    -f file     : create a backup file and its absolut path is specify by 'file'.
    default is backup file name by timestamp.


restore [-i index|-f file]     
    restore with a backup file at current container
    -i index    : resotre with a backup file specify by index.
    -f file     : resotre with a backup file specify by file path.
    default is restore by index and index=1.

version|-V|--version
    show the version.

help|-h|--help        
    show this usage.

examples:
1. sky list 
2. sky clean
3. sky clean -a
4. sky backup -f /backup/container_redis/uuid_123.tar
5. sky bakup
6. sky restore -i 2

At the same time, you can see logfile at $LOG_FILE.

This script is placed in container's directory: /usr/local/bin/.
If you want to execute script outside container, the command would be:
docker exec <container_name> sky backup
"
    exit 0
}
```
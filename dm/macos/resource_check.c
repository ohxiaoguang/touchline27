// SPDX-License-Identifier: MIT
// macOS front end: read this App's prepared module list and verify a selection
// against it. The container knowledge and the comparison itself are the shared
// reader's (nxrom_verify); iOS launchers call the same function through
// ResourceDiscovery.swift, so both platforms accept exactly the same files.
#include "../resource/nxrom.h"
#include <errno.h>
#include <stdio.h>
#include <string.h>

#define MODULES 64

int dm_mac_resources_check(const char *base,const char *update,const char *keys,
                           const char *manifest,uint64_t title,char *error,size_t capacity) {
    char names[MODULES][64], builds[MODULES][33];
    const char *module[MODULES], *build[MODULES];
    FILE *f=fopen(manifest,"r"); int result=-1; size_t count=0;
    if(!f) { snprintf(error,capacity,"Prepared module metadata is unavailable"); goto done; }
    char line[256],extra;
    while(fgets(line,sizeof line,f)) {
        if(count==MODULES) { snprintf(error,capacity,"Invalid prepared module metadata"); goto done; }
        if(sscanf(line,"%63s %32[0-9a-fA-F] %c",names[count],builds[count],&extra)!=2 || strlen(builds[count])!=32) {
            snprintf(error,capacity,"Invalid prepared module metadata"); goto done;
        }
        module[count]=names[count]; build[count]=builds[count]; count++;
    }
    if(ferror(f) || !count) { snprintf(error,capacity,"Cannot read prepared module metadata"); goto done; }
    result=nxrom_verify(base,update,keys,title,module,build,count,error,capacity);
done:
    if(f) fclose(f);
    if(result) errno=EINVAL;
    return result;
}

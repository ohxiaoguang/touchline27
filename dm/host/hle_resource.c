#define _DARWIN_C_SOURCE
// Keep the portable reader independent of HLE and game profiles.
#include "../resource/nxdata.c"

#include "../resource/nxrom.c"

#include "game_profile.h"
// Front ends validate without starting guest code; actual mount owns its own view.
int dm_external_resource_check_paths(const char *base, const char *update, const char *keys,
                                     char *error, size_t capacity) {
    nxrom *fs=NULL;
    int r=nxrom_open(base,update,keys,strtoull(DM_GAME_ID,NULL,16),&fs,error,capacity);
    nxrom_close(fs); return r;
}
int dm_external_resource_check(char *error, size_t capacity) {
    const char *backend=getenv("DM_RESOURCE_BACKEND");
    if (!backend || strcmp(backend,"nsp")) return 0;
    return dm_external_resource_check_paths(getenv("DM_RESOURCE_NSP"),getenv("DM_RESOURCE_UPDATE"),getenv("DM_RESOURCE_KEYS"),error,capacity);
}

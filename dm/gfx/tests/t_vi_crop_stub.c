// A VI provider for NVN queue snapshot tests, linked as a separate translation unit.
#include <string.h>
static int crop[4];
void test_set_vi_crop(const int value[4]) { memcpy(crop,value,sizeof crop); }
void dm_vi_layer_crop(int out[4]) { memcpy(out,crop,sizeof crop); }

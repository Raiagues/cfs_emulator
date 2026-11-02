#ifndef TMP105_LIB_INTERNAL_H
#define TMP105_LIB_INTERNAL_H

#include "tmp105_lib.h"

#define TMP105_TEMPERATURE_REGISTER 0x00
#define TMP105_SIGN_BIT 0x8000
/* D3-D0 of the temperature register always read 0 on a TMP105. */
#define TMP105_UNUSED_BITS 0x000F
#define TMP105_FULL_SCALE 65536
#define TMP105_MILLIDEGREES 1000
#define TMP105_COUNTS_PER_CELSIUS 256

#endif

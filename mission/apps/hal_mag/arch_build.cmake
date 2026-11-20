###########################################################
#
# HAL_MAG platform build setup
#
# This file is evaluated as part of the "prepare" stage
# and can be used to set up prerequisites for the build,
# such as generating header files
#
###########################################################

# The list of header files that control the HAL_MAG configuration
set(HAL_MAG_PLATFORM_CONFIG_FILE_LIST
  hal_mag_internal_cfg_values.h
  hal_mag_platform_cfg.h
  hal_mag_perfids.h
  hal_mag_msgids.h
  hal_mag_msgid_values.h
)

generate_configfile_set(${HAL_MAG_PLATFORM_CONFIG_FILE_LIST})


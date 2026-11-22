###########################################################
#
# HAL_TEMP platform build setup
#
# This file is evaluated as part of the "prepare" stage
# and can be used to set up prerequisites for the build,
# such as generating header files
#
###########################################################

# The list of header files that control the HAL_TEMP configuration
set(HAL_TEMP_PLATFORM_CONFIG_FILE_LIST
  hal_temp_internal_cfg_values.h
  hal_temp_platform_cfg.h
  hal_temp_perfids.h
  hal_temp_msgids.h
  hal_temp_msgid_values.h
)

generate_configfile_set(${HAL_TEMP_PLATFORM_CONFIG_FILE_LIST})


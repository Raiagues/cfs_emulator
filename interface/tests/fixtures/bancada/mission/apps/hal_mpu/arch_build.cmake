###########################################################
#
# HAL_MPU platform build setup
#
# This file is evaluated as part of the "prepare" stage
# and can be used to set up prerequisites for the build,
# such as generating header files
#
###########################################################

# The list of header files that control the HAL_MPU configuration
set(HAL_MPU_PLATFORM_CONFIG_FILE_LIST
  hal_mpu_internal_cfg_values.h
  hal_mpu_platform_cfg.h
  hal_mpu_perfids.h
  hal_mpu_msgids.h
  hal_mpu_msgid_values.h
)

generate_configfile_set(${HAL_MPU_PLATFORM_CONFIG_FILE_LIST})


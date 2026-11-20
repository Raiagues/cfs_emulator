###########################################################
#
# HAL_MPU mission build setup
#
# This file is evaluated as part of the "prepare" stage
# and can be used to set up prerequisites for the build,
# such as generating header files
#
###########################################################

# The list of header files that control the HAL_MPU configuration
set(HAL_MPU_MISSION_CONFIG_FILE_LIST
  hal_mpu_fcncode_values.h
  hal_mpu_interface_cfg_values.h
  hal_mpu_mission_cfg.h
  hal_mpu_perfids.h
  hal_mpu_msg.h
  hal_mpu_msgdefs.h
  hal_mpu_msgstruct.h
  hal_mpu_tbl.h
  hal_mpu_tbldefs.h
  hal_mpu_tblstruct.h
  hal_mpu_topicid_values.h
)

generate_configfile_set(${HAL_MPU_MISSION_CONFIG_FILE_LIST})


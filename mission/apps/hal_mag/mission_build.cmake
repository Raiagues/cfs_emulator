###########################################################
#
# HAL_MAG mission build setup
#
# This file is evaluated as part of the "prepare" stage
# and can be used to set up prerequisites for the build,
# such as generating header files
#
###########################################################

# The list of header files that control the HAL_MAG configuration
set(HAL_MAG_MISSION_CONFIG_FILE_LIST
  hal_mag_fcncode_values.h
  hal_mag_interface_cfg_values.h
  hal_mag_mission_cfg.h
  hal_mag_perfids.h
  hal_mag_msg.h
  hal_mag_msgdefs.h
  hal_mag_msgstruct.h
  hal_mag_tbl.h
  hal_mag_tbldefs.h
  hal_mag_tblstruct.h
  hal_mag_topicid_values.h
)

generate_configfile_set(${HAL_MAG_MISSION_CONFIG_FILE_LIST})


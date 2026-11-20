###########################################################
#
# HAL_TEMP mission build setup
#
# This file is evaluated as part of the "prepare" stage
# and can be used to set up prerequisites for the build,
# such as generating header files
#
###########################################################

# The list of header files that control the HAL_TEMP configuration
set(HAL_TEMP_MISSION_CONFIG_FILE_LIST
  hal_temp_fcncode_values.h
  hal_temp_interface_cfg_values.h
  hal_temp_mission_cfg.h
  hal_temp_perfids.h
  hal_temp_msg.h
  hal_temp_msgdefs.h
  hal_temp_msgstruct.h
  hal_temp_tbl.h
  hal_temp_tbldefs.h
  hal_temp_tblstruct.h
  hal_temp_topicid_values.h
)

generate_configfile_set(${HAL_TEMP_MISSION_CONFIG_FILE_LIST})


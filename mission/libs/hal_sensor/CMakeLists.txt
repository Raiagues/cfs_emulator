project(CFE_HAL_SENSOR C)

add_cfe_app(hal_sensor fsw/src/hal_sensor.c)
target_include_directories(hal_sensor PUBLIC fsw/public_inc)

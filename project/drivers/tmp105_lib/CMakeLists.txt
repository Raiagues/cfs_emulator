project(CFE_TMP105_LIB C)

add_cfe_app(tmp105_lib fsw/src/tmp105_lib.c)
target_include_directories(tmp105_lib PUBLIC fsw/public_inc)
add_cfe_app_dependency(tmp105_lib linux_i2c_lib)

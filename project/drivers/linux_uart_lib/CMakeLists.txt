project(CFE_LINUX_UART_LIB C)

add_cfe_app(linux_uart_lib fsw/src/linux_uart_lib.c)
target_include_directories(linux_uart_lib PUBLIC fsw/public_inc)

chcp 65001

@echo off





%~d0    %进入这个脚本执行的盘符%
cd %~dp0   %进入这个脚本执行的目录%


nuclei -h

@echo.
@echo.*********************使用说明*********************
@echo.
@echo. 使用:  .\nuclei.exe -h
@echo.
@echo.
@echo. 如果漏洞模块的问题报错说没有模块就可以使指定我在官方github下载的模块，运行如下
@echo. 使用:  .\nuclei.exe -t nuclei-templates
@echo.
@echo. 自行下载方法如下
@echo. 如果下载失败可以自己下载模块地址：https://github.com/projectdiscovery/nuclei
@echo. 把下载好的文件放到windows的用户目录下比如：C:\Users\xxxx\
@echo "******************************************************
cmd
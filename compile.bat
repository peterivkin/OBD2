:: briefcase update android -r
:: После изменения pyproject.toml нужно сказать Briefcase, чтобы он пересобрал окружение приложения и включил туда новую библиотеку:

::briefcase create android
set HTTP_PROXY=
set HTTPS_PROXY=
set ALL_PROXY=
briefcase update android 
briefcase build android


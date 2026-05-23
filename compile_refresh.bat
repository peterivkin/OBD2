::C:\WORK\OBD2\obd2\build\obd2\android\gradle\gradlew.bat --stop

::briefcase build android
:: Запуск из под админа !!!!!!!!!!!!!!!!!!!

rmdir /s /q "C:\WORK\OBD2\obd2\build\obd2\android"
cd C:\WORK\OBD2\obd2
briefcase create android
briefcase build android
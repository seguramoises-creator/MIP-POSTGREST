# Descargas servidas por la suite

Lo que se copie aquí queda disponible en `https://<servidor>/descargas/<fichero>`.

El APK de la app de campo debe llamarse **`vista-campo.apk`** — es el nombre que busca
la pantalla «App de campo» de la suite.

Para publicar una versión nueva NO hace falta reconstruir ni redesplegar el frontend:
la carpeta va montada como volumen, así que basta con copiar el fichero encima.

    scp bin/Release/net10.0-android/publish/com.vistamip.campo-Signed.apk \
        usuario@servidor:/opt/msm-pg/descargas/vista-campo.apk

Los `.apk` NO se versionan en git: son decenas de megas y cambian en cada compilación.

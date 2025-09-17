# Scraper de Convocatorias Internacionales y Nacionales para Investigación

Este repositorio contiene un conjunto de scripts en Python que permiten
consultar convocatorias de financiación para investigación tanto en portales
internacionales como en ministerios colombianos. La interfaz se construye
con Tkinter, y ofrece dos modos de operación: Internacional y
Nacional. En el modo internacional se consulta la Comisión Europea,
Wellcome Trust, la Academia de Finlandia (AKA), ANR, IBRO e IDRC; en el modo
nacional se revisan varias páginas oficiales de ministerios colombianos. El
programa resume las descripciones de las convocatorias y clasifica cada
convocatoria de acuerdo con los Objetivos de Desarrollo Sostenible (ODS) a
partir de palabras clave
raw.githubusercontent.com
. Los resultados pueden
guardarse en ficheros CSV para consultarlos posteriormente sin volver a
scrapear las páginas web.

---

## Requisitos de instalación

Antes de ejecutar la aplicación es necesario instalar Python 3.8 o superior y
varias bibliotecas. Se recomienda crear un entorno virtual para aislar las
dependencias. Las bibliotecas que utiliza el proyecto incluyen:

- Tkinter – interfaz gráfica (incluida con Python).

- selenium – para automatizar el navegador en los portales que requieren
interacción dinámica; se configura un ChromeDriver en modo headless para
evitar ventanas de navegador
raw.githubusercontent.com
.

- requests y BeautifulSoup – empleados por los scrapers que usan
HTTP simple; se establece una cabecera de User‑Agent para reducir
bloqueos por parte de los servidores
raw.githubusercontent.com
.

- bs4 (BeautifulSoup4) – análisis de HTML.

Para instalar las dependencias básicas en un entorno virtual puede ejecutar
los siguientes comandos:

```bash
python3 -m venv venv
source venv/bin/activate
pip install selenium requests beautifulsoup4 
```
**Nota sobre Selenium:** el código utiliza un controlador de Google
Chrome en modo “headless”. Es necesario tener instalado Chrome
(o Chromium) y disponer de un ejecutable de chromedriver compatible en
el PATH del sistema. Consulte la [documentación de Selenium](https://selenium-python.readthedocs.io) para
instalar el controlador correspondiente.

---

## Ejecución de la interfaz

1. Descargue este repositorio (por ejemplo con git clone).

2. Instale las dependencias según la sección anterior.

3. Ejecute la aplicación con:

```bash
python3 main_gui.py
```

La ventana principal se abrirá mostrando una lista desplegable para
seleccionar el modo de operación. A continuación se presentan los
formularios de búsqueda dependiendo del modo elegido.

---

## Manual de uso

### Modo Internacional

Este modo replica la funcionalidad original para consultar convocatorias en
portales internacionales. Los pasos de uso son:

1. Seleccionar un tema en el campo “Line Theme”. Se muestra un listado
predefinido de temas populares, aunque también puede dejarse vacío para
realizar una búsqueda más amplia. El tema se utiliza como palabra
clave en el portal y sirve de filtro inicial.

2. Seleccionar un ODS (opcional) en la lista “SDG”. Si se elige
alguno de los 17 objetivos, sólo se mostrarán convocatorias cuya
descripción contenga palabras relacionadas con ese objetivo. La
clasificación utiliza un mapeo local de palabras clave.

3. Introducir palabras clave adicionales en el cuadro “Keywords”. Se
realizará una coincidencia en el título y en la descripción. (No es obligatorio sino a comodidad del Usuario) 

4. Elegir un portal en el campo “Funding portal”: European Commission,
Wellcome, Academy of Finland, ANR, IBRO, IDRC o “All” para consultar
todas las fuentes. Al seleccionar “All” la aplicación obtendrá hasta
diez convocatorias por portal.

5. Pulse “Search Online” para realizar el scraping. Se abrirá un
navegador headless mediante Selenium, se accederá a los portales
seleccionados y se extraerán hasta diez convocatorias por sitio. Para
cada convocatoria se almacena el título, el enlace, fechas de apertura
y cierre, una descripción resumida y la clasificación ODS. Si
existe una versión en cache que aún es válida (la convocatoria cierra
dentro de más de siete días), el resultado se carga desde el archivo
CSV correspondiente en data/cache.

6. Opcionalmente pulse “Search CSV” para volver a cargar los
resultados almacenados en el disco sin realizar scraping. Esto es útil
si se desea revisar convocatorias anteriores sin conexión.

7. Pulse “Clear” para limpiar todos los campos y resultados.

La tabla de resultados muestra las convocatorias numeradas. El enlace es
clicable y se abre en el navegador predeterminado. También se indican
las fechas de apertura y cierre, el portal de origen, un resumen y la
lista de ODS detectados. Estos resultados se guardan en el fichero
data/scraping_results/calls_for_proposals.csv.

### Modo Nacional

En este modo se consultan convocatorias abiertas en los ministerios
colombianos. Los pasos son:

1. Seleccionar el ministerio en la lista “Ministerio”. Las opciones
incluyen MinEnergía, MinAmbiente, MinCiencias, MinCultura, MinTIC,
MinEducación o “All” para consultar todos los ministerios.

2. Seleccionar el tipo de convocatoria: “Regalías”, “Proyectos” o
“All”. Algunas entidades sólo publican uno de los tipos. La lista
se utiliza para filtrar los resultados. Se mostrarán hasta diez
convocatorias por ministerio.

3. Pulse “Search Online” para ejecutar los scrapers específicos de
cada ministerio. Estos scrapers usan peticiones HTTP sencillas y
recogen el título, enlace, fechas y una descripción resumida. Las
convocatorias se ordenan de manera que las que tienen fecha de cierre
cercana aparecen primero; aquellas sin fecha explícita se ordenan por
fecha de apertura o por orden alfabético, según corresponda.

4. Pulse “Search CSV” para cargar los datos guardados en data/cache.

5. Pulse “Clear” para restablecer los filtros.

En el modo nacional la clasificación ODS se establece como unknown, ya
que las descripciones de los ministerios suelen ser breves. Al igual que
en el modo internacional, los resultados se guardan en un archivo CSV.

---

## Caché y almacenamiento de resultados

El sistema mantiene un mecanismo de caché para evitar scrapear la misma
información en cada búsqueda. Cuando se realiza una consulta, los
resultados se guardan en data/cache utilizando un nombre de archivo
compuesto por el portal o ministerio, el tema y el ODS seleccionados. Al
iniciar una nueva búsqueda, se cargan los datos almacenados y se filtran
las convocatorias que vencen en los próximos siete días.

Si no hay suficientes convocatorias en la caché, el scraper se ejecuta
nuevamente y los nuevos resultados se fusionan con los existentes. El
CSV global con los resultados de la última búsqueda se guarda en
data/scraping_results/calls_for_proposals.csv.

## Personalización del resumen y clasificación de ODS

El módulo summarizer.py implementa un resumen sencillo y un clasificador
de ODS basado en palabras clave. Si la biblioteca Gensim u otros
algoritmos de resumen no están disponibles, la función summarize_text()
simplemente recorta el texto a los primeros word_limit términos. El
clasificador de ODS busca términos asociados con cada uno de los 17
objetivos y devuelve una lista con los números de los ODS encontrados. Si
no encuentra coincidencias devuelve ['unknown']. Puede ajustar las
palabras clave en _SDG_KEYWORDS dentro de summarizer.py para mejorar
la clasificación o adaptarla a otros idiomas.

## Estructura de archivos

- main_gui.py – punto de entrada de la aplicación gráfica; define la
interfaz, maneja la selección de modo y orquesta las funciones de
scraping y de caché.

- utils.py – utilidades para crear un WebDriver de Chrome en modo
headless y normalizar cadenas a slugs.

- http_utils.py – funciones sencillas basadas en requests y
BeautifulSoup; añaden un User-Agent para evitar respuestas 403.

- summarizer.py – genera resúmenes truncados y clasifica convocatorias
por ODS mediante mapeos de palabras clave.

- X_scraper.py – módulos de scraping específicos para cada portal o
ministerio (por ejemplo eu_scraper.py, wellcome_scraper.py,
minenergia_scraper.py, etc.). Cada función devuelve una lista de
diccionarios con las claves: title, link, opening_date,
deadline_date, description, ods_list, site y, en el caso
nacional, type.

- data/cache/ – almacena los archivos CSV de caché separados por
filtros. Esta carpeta se crea automáticamente si no existe.

- data/scraping_results/ – contiene el CSV con los resultados de la
última búsqueda.

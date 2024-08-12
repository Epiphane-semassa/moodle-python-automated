import os
import subprocess
import urllib.request
import zipfile
import psycopg2
from tqdm import tqdm
import shutil
import time
import threading
from dotenv import load_dotenv


# Charger les variables d'environnement depuis le fichier .env
load_dotenv()

POSTGRES_HOST = os.getenv('POSTGRES_HOST')
POSTGRES_PORT = os.getenv('POSTGRES_PORT')
POSTGRES_USER = os.getenv('POSTGRES_USER')
POSTGRES_PASSWORD = os.getenv('POSTGRES_PASSWORD')
MOODLE_DB_NAME = os.getenv('MOODLE_DB_NAME')
MOODLE_DB_USER = os.getenv('MOODLE_DB_USER')
MOODLE_DB_PASS = os.getenv('MOODLE_DB_PASS')
MOODLE_ROOT_DATA = os.getenv('MOODLE_ROOT_DATA')
MOODLE_WWWROOT = os.getenv('MOODLE_WWWROOT')
MOODLE_LANG = os.getenv('MOODLE_LANG')
MOODLE_DBTYPE = os.getenv('MOODLE_DBTYPE')
MOODLE_FULLNAME = os.getenv('MOODLE_FULLNAME')
MOODLE_SHORTNAME = os.getenv('MOODLE_SHORTNAME')
MOODLE_ADMIN_USER = os.getenv('MOODLE_ADMIN_USER')
MOODLE_ADMIN_PASS = os.getenv('MOODLE_ADMIN_PASS')
MOODLE_ADMIN_EMAIL = os.getenv('MOODLE_ADMIN_EMAIL')


def download_file(url, dest):
    print(f"\n Téléchargement de {url}")

    # Ouverture de l'URL et du fichier de destination
    with urllib.request.urlopen(url) as response, open(dest, 'wb') as out_file:
        total_length = int(response.getheader('content-length'))
        block_size = 1024  # Taille du bloc de téléchargement (1KB)
        t = tqdm(total=total_length, unit='B', unit_scale=True, desc=dest)

        # Télécharger le fichier par blocs
        while True:
            buffer = response.read(block_size)
            if not buffer:
                break
            out_file.write(buffer)
            t.update(len(buffer))

    print(f"Téléchargement terminé : {dest}")
    if os.path.getsize(dest) == 0:
        raise Exception("Le fichier téléchargé est vide")


def extract_zip(file, path):
    print(f"\nExtraction de {file} vers {path}")
    if zipfile.is_zipfile(file):
        with zipfile.ZipFile(file, 'r') as zip_ref:
            zip_ref.extractall(path)
        print("Extraction terminée")
    else:
        raise zipfile.BadZipFile(f"Le fichier {file} n'est pas un fichier ZIP valide")


def move_moodle_contents(src_folder, dest_folder):
    # Obtenir la liste des fichiers et des dossiers dans le dossier source
    items = os.listdir(src_folder)

    for item in items:
        # Obtenir le chemin complet des éléments source et destination
        src_path = os.path.join(src_folder, item)
        dest_path = os.path.join(dest_folder, item)

        # Déplacer chaque élément du dossier source vers le dossier destination
        if os.path.isdir(src_path):
            shutil.move(src_path, dest_path)
        else:
            shutil.move(src_path, dest_folder)


def create_database():
    print("\n")
    global connection, cursor
    try:
        connection = psycopg2.connect(
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD,
            host=POSTGRES_HOST,
            port=POSTGRES_PORT
        )
        connection.autocommit = True
        cursor = connection.cursor()

        # Vérifier si l'utilisateur existe déjà
        cursor.execute(f"SELECT 1 FROM pg_roles WHERE rolname='{MOODLE_DB_USER}';")
        user_exists = cursor.fetchone()

        if not user_exists:
            cursor.execute(f"CREATE USER {MOODLE_DB_USER} WITH ENCRYPTED PASSWORD '{MOODLE_DB_PASS}';")
            print("Utilisateur moodleuser créé avec succès")

        # Vérifier si la base de données existe déjà
        cursor.execute(f"SELECT 1 FROM pg_database WHERE datname='{MOODLE_DB_NAME}';")
        db_exists = cursor.fetchone()

        if not db_exists:
            cursor.execute(f"CREATE DATABASE pymoodle WITH OWNER {MOODLE_DB_USER};")
            print("Base de données moodle créée avec succès")
        else:
            print("La base de données moodle existe déjà")

        # Attribuer les privilèges indépendamment de la création de l'utilisateur
        # cursor.execute("GRANT ALL PRIVILEGES ON DATABASE pymoodle TO pymoodleuser;")
        # print("Privilèges accordés à pymoodleuser sur la base de données pymoodle")

        # cursor.execute("CREATE USER pymoodleuser WITH PASSWORD 'pymoodleuser';")
        # cursor.execute("CREATE DATABASE pymoodle WITH OWNER pymoodleuser;")

        print("Base de données et utilisateur créés avec succès")

    except (Exception, psycopg2.Error) as error:
        print("\n Erreur lors de la création de la base de données et de l'utilisateur", error)
    finally:
        if connection:
            cursor.close()
            connection.close()


def run_install_script(moodle_path, config_exists):
    install_script = os.path.join(moodle_path, "admin", "cli", "install.php")
    install_database_script = os.path.join(moodle_path, "admin", "cli", "install_database.php")
    if not config_exists:
        subprocess.run(["php", install_script,
                        "--chmod=0777",
                        f"--lang={MOODLE_LANG}",
                        f"--wwwroot={MOODLE_WWWROOT}",
                        f"--dataroot={MOODLE_ROOT_DATA}",
                        f"--dbtype={MOODLE_DBTYPE}",
                        f"--dbname={MOODLE_DB_NAME}",
                        f"--dbuser={MOODLE_DB_USER}",
                        f"--dbpass={MOODLE_DB_PASS}",
                        f"--fullname={MOODLE_FULLNAME}",
                        f"--shortname={MOODLE_SHORTNAME}",
                        f"--adminuser={MOODLE_ADMIN_USER}",
                        f"--adminpass={MOODLE_ADMIN_PASS}",
                        f"--adminemail={MOODLE_ADMIN_EMAIL}",
                        "--non-interactive",
                        "--agree-license"])
    else:
        subprocess.run(["php", install_database_script,
                        f"--adminuser={MOODLE_ADMIN_USER}",
                        f"--adminpass={MOODLE_ADMIN_PASS}",
                        f"--adminemail={MOODLE_ADMIN_EMAIL}",
                        "--agree-license"])


def assign_manager_role():
    global connection, cursor
    try:
        connection = psycopg2.connect(
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD,
            host=POSTGRES_HOST,
            port=POSTGRES_PORT,
            database=MOODLE_DB_NAME
        )
        cursor = connection.cursor()

        # Obtenir l'ID du rôle manager
        cursor.execute("SELECT id FROM mdl_role WHERE shortname = 'manager';")
        role_id = cursor.fetchone()[0]

        # Obtenir l'ID de l'utilisateur administrateur
        cursor.execute(f"SELECT id FROM mdl_user WHERE username = '{MOODLE_ADMIN_USER}';")
        user_id = cursor.fetchone()[0]

        # Exécuter la requête d'insertion
        cursor.execute(
            """
            INSERT INTO mdl_role_assignments (roleid, contextid, userid, timemodified, modifierid, component, itemid, sortorder)
            VALUES (%s, 1, %s, EXTRACT(EPOCH FROM NOW()), %s, '', 0, 0);
            """,
            (role_id, user_id, user_id)
        )

        connection.commit()
        print("\nRôle de manager assigné à l'utilisateur administrateur avec succès")

    except (Exception, psycopg2.Error) as error:
        print("\nErreur lors de l'assignation du rôle de manager : ", error)
    finally:
        if connection:
            cursor.close()
            connection.close()


def run_cron_job(moodle_path):
    cron_script = os.path.join(moodle_path, "admin", "cli", "cron.php")
    while True:
        subprocess.run(['php', cron_script], shell=True)
        time.sleep(60)


def schedule_cron_job(moodle_path):
    thread = threading.Thread(target=run_cron_job, args=(moodle_path,))
    thread.daemon = True
    thread.start()
    print("\nTâche cron programmée pour s'exécuter chaque minute")


def start_web_server(web_server_path):
    apache_start = os.path.join(web_server_path, "apache_start.bat")
    subprocess.run(apache_start, shell=True)
    print("\nServeur web démarré avec succès!")


def main():
    moodle_url = "https://packaging.moodle.org/stable404/moodle-latest-404.zip"
    moodle_zip = "C:\\dev\\pymoodle.zip"
    web_server_path = "C:\\xampp"
    web_server_sitedocs_path = os.path.join(web_server_path, "htdocs")
    moodle_path = os.path.join(web_server_sitedocs_path, "pymoodle")

    # Vérifier si le fichier zip existe déjà
    if not os.path.exists(moodle_zip):
        # Télécharger Moodle
        download_file(moodle_url, moodle_zip)
    else:
        print(f"{moodle_zip} existe déjà. Téléchargement ignoré.")

    if not os.path.exists(moodle_path):
        # Extraire Moodle dans le répertoire htdocs de XAMPP
        extract_zip(moodle_zip, moodle_path)
    else:
        print(f"{moodle_path} existe déjà. Extraction ignorée.")

    # Déplacer le contenu du sous-dossier moodle/moodle vers le dossier moodle principal
    inner_moodle_path = os.path.join(moodle_path, "moodle")
    if os.path.exists(inner_moodle_path):
        move_moodle_contents(inner_moodle_path, moodle_path)
        # Supprimer le dossier vide moodle/moodle
        os.rmdir(inner_moodle_path)

    # Créer la base de données et l'utilisateur PostgreSQL
    create_database()

    # Vérifier si config.php existe
    config_path = os.path.join(moodle_path, "config.php")
    config_exists = os.path.exists(config_path)

    # Exécuter le script d'installation Moodle
    run_install_script(moodle_path, config_exists)

    assign_manager_role()

    # Programmer la tâche cron
    schedule_cron_job(moodle_path)

    # Lancer Web server
    # apache_start = os.path.join(web_server_path, "apache_start.bat")
    # subprocess.run(apache_start, shell=True)
    schedule_cron_job(moodle_path)
    thread = threading.Thread(target=start_web_server, args=(web_server_path,))
    thread.daemon = True
    thread.start()

    print("\n Installation de Moodle terminée. Accédez à http://localhost/pymoodle pour terminer la configuration via "
          "le navigateur.")


if __name__ == "__main__":
    main()

# MailFlow — stack Docker Compose (hôte m720q)

## Maintenance — chemin simple

- Configuration : `compose.yaml` + surcharge locale `compose.override.yaml`, désormais en YAML lisible, sans changement de configuration effective. Les mentions JSON plus bas décrivent l’ancien format.
- Sauvegarde : le script nocturne existant `backup.sh`, pas de nouveau service. Il sauvegarde Postgres, pas la configuration ni Redis. Un sommaire valide ne prouve pas une restauration.
- Avant mise à jour : vérifier une sauvegarde et identifier le point de retour. Les fichiers `candidate` et `.bak` restent conservés mais ne sont pas la configuration courante.
- Contrôles : `docker compose config --quiet`, `docker compose ps`, `tail -n 5 backups/backup.log`. Ne pas partager la configuration complète : elle peut contenir des secrets.

Dépôt de configuration de la stack MailFlow. Il ne contient que la configuration écrite à la main. Les données, les sauvegardes, les secrets et les fichiers `.bak-*` restent locaux et sont ignorés par git.

État documenté au 2026-11-03 (mise à jour 4.2.0, Redis 7.4.12 et synchro toutes les 10 minutes ; l'audit du 2026-11-02 reste la base, et certaines sections datées conservent leur date propre), à partir des fichiers du dépôt, de fichiers locaux cités dans le texte (dont le dossier `backups/` et le lien `/home/m720q/mailflow`), de la crontab de l'utilisateur m720q (`crontab -l`) et de la sortie de `tailscale serve status`. Tout ce qui n'a pas été contrôlé est marqué « non vérifié ».

## Fichiers suivis par git

- `compose.yaml` : définition des services, valeurs par défaut des variables, profil `https`.
- `compose.override.yaml` : surcharge fusionnée automatiquement par `docker compose`. Fixe les images par digest, `NGINX_TLS=off`, les limites mémoire, la rotation des journaux et l'URL tailnet. Le fichier est en JSON (extension `.yaml`), donc sans commentaires.
- `backup.sh` : sauvegarde de la base (voir « Sauvegardes »).
- `.gitignore`.

Ignorés (présents localement) : `.env` et `.env.bak-*`, `backups/`, `compose.gsd-005.candidate.yaml`, les `compose.*.bak-*`, `docker-compose.override.yml.bak-gsd-005-20261027-181231`. Le dossier `certs/` (vide actuellement) est ignoré par `.gitignore` (règle `certs/`).

## Services

| Service | Conteneur | Image | Ports publiés | Volume | Remarques |
|---|---|---|---|---|---|
| frontend | `mailflow-frontend` | `ghcr.io/maathimself/mailflow-frontend` (digest) | `127.0.0.1:${APP_PORT:-18443}` → 443 ; `127.0.0.1:${APP_HTTP_PORT:-18081}` → 80 | `./certs` → `/etc/nginx/ssl` | Selon le commentaire de `compose.yaml` (l. 25-26), avec `NGINX_TLS=off` seul le port 80 sert HTTP. Healthcheck sur `http://127.0.0.1:80/`. |
| backend | `mailflow-backend` | `ghcr.io/maathimself/mailflow-backend` (digest) | aucun | aucun | Port interne 3000. Healthcheck `/api/health`. Démarre après postgres et redis (healthy). `stop_grace_period` 30 s. |
| postgres | `mailflow-postgres` | `postgres` (digest) | aucun | `postgres_data` → `/var/lib/postgresql/data` | Le tag d'origine `postgres:16-alpine` est remplacé par le digest dans l'override. Version exacte : non vérifié. |
| redis | `mailflow-redis` | `redis` (digest) | aucun | `redis_data` → `/data` | Sessions et cache. Mot de passe lu depuis `REDIS_PASSWORD` (`--requirepass`). Le tag d'origine `redis:7-alpine` est remplacé par le digest. |
| caddy | `mailflow-caddy` | `caddy:2-alpine` | `80`, `443/tcp`, `443/udp` sans adresse de liaison dans `compose.yaml` (l. 141-144), donc sur toutes les interfaces par défaut de Docker | `caddy_data`, `caddy_config` | Profil `https` uniquement : non démarré par défaut. Voir « Accès et réseau ». |

Réseau : bridge `mailflow`. Noms réels des volumes Docker (préfixés par le nom du projet) : non vérifié.

## Lancement

Depuis le dossier du projet :

    docker compose up -d

`compose.override.yaml` est lu automatiquement. Sans ce fichier, les images reviennent à `${MAILFLOW_VERSION:-latest}` et `NGINX_TLS` vaut sa valeur vide par défaut. Le comportement dans ce cas : non vérifié.

L'en-tête de `compose.yaml` (l. 1-10) décrit une installation amont (`docker-compose.ghcr.yml`, `.env.example`, `curl`) qui n'existe pas dans ce dépôt. Ne pas suivre cette procédure.

Chemin : `/home/m720q/mailflow` est un lien symbolique vers `/home/m720q/projects/mailflow`. Le cron et `backup.sh` utilisent le premier chemin.

## Accès et réseau

- Accès prévu : tailnet Tailscale. Depuis le 2026-10-31, `APP_URL` et `FRONTEND_URL` valent `https://mailflow.taild49e80.ts.net` (`compose.override.yaml`, sauvegarde `.bak-pre-service-url-20261031` ; backend recréé, sessions Redis conservées). Avant : `https://m720q.taild49e80.ts.net:10000`, qui répond toujours (HTTP 200) et sert de contrôle de vie pour la bascule.
- Depuis le 2026-10-31, le Service Tailscale `svc:mailflow` (`https://mailflow.taild49e80.ts.net`, VIP 100.105.105.253) est aussi annoncé par m720q (même cible `http://127.0.0.1:18081`). C'est l'adresse officielle depuis le 2026-10-31. Voir « Redondance ».
- Mapping côté hôte : `tailscale serve` https `:10000` → `http://127.0.0.1:18081`, Tailscale termine le TLS. Source écrite : ligne 1 de `docker-compose.override.yml.bak-gsd-005-20261027-181231` (fichier ignoré). Confirmé par `tailscale serve status` le 2026-10-30. Commande exacte de `tailscale serve` : non vérifié.
- `NGINX_TLS=off` : d'après le commentaire du même fichier (l. 12), le cookie de session garde son drapeau `Secure` grâce à `X-Forwarded-Proto: https` transmis par le proxy. Comportement réel du cookie : non vérifié (code du backend absent du dépôt).
- `TRUST_PROXY_HOPS` : vide par défaut dans `compose.yaml`. Nombre de sauts requis : non vérifié.
- `MS_REDIRECT_URI` et `GOOGLE_REDIRECT_URI` : valeurs non documentées ici. Valeurs effectives et origine (`.env`) : non vérifié, `.env` n'a pas été lu.
- Profil `https` (Caddy) : d'après le commentaire de `compose.yaml` (l. 25-26), `NGINX_TLS=off` ne sert que le port 80, alors que Caddy relaie vers `frontend:443` avec `tls_insecure_skip_verify` (`compose.yaml` l. 177-179). Le profil ne fonctionnerait donc pas en l'état : non vérifié, non testé. Le commentaire du service `caddy` (l. 133-134, et non l'en-tête l. 1-10) cite `docker-compose.https.yml`, absent du dépôt.

## Variables d'environnement (noms uniquement)

Le fichier `.env` est à la racine, ignoré par git. Son contenu n'est pas documenté ici. Il n'y a pas de `.env.example` dans le dépôt.

- Sans valeur par défaut dans `compose.yaml` : `SESSION_SECRET`, `DB_PASSWORD`, `REDIS_PASSWORD`.
- Valeur par défaut vide : `APP_URL`, `ENCRYPTION_KEY` (voir ci-dessous), `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`, `VAPID_SUBJECT`, `IMAP_MAX_PERSISTENT_PER_HOST`, `TRUST_PROXY_HOPS`, `MS_BUILTIN_APP`, `MS_CLIENT_ID`, `MS_CLIENT_SECRET`, `MS_TENANT_ID`, `MS_REDIRECT_URI`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI`, `NGINX_TLS`, `ACME_EMAIL`.
- Valeur par défaut non vide : `MAILFLOW_VERSION` (`latest`), `APP_PORT` (`18443`), `APP_HTTP_PORT` (`18081`), `DB_HOST` (`postgres`), `DB_PORT` (`5432`), `DB_NAME` (`mailflow`), `DB_USER` (`mailflow`), `DOMAIN` (`localhost`).
- `ENCRYPTION_KEY` : d'après l'audit du 2026-11-02, cette clé n'existe que dans `.env` (valeur non lue pour cette mise à jour). Elle n'est ni dans `compose.yaml` (défaut vide), ni dans le dépôt git, ni dans les dumps `pg_dump`. Elle voyage donc seulement avec les copies de `.env` (`.env.bak-*`, `backups/pre-4.0.5-*/.env`, pile de secours pi5max). Perdre `.env` = perdre la clé : en garder une copie hors de la machine, et ne pas la régénérer. Ce que la clé protège exactement et ce qui se passe si elle est vide ou différente : non vérifié (le code du backend n'est pas dans ce dépôt).

## Images et versions

- Les images backend et frontend, ainsi que postgres et redis, sont figées par digest dans `compose.override.yaml`. Ces digests sont ceux de `compose.override.yaml` dans HEAD (fichier identique à HEAD au contrôle du 2026-11-03). La clé `image` de l'override remplace celle de `compose.yaml` (l. 18 et 43). `MAILFLOW_VERSION` n'a donc aucun effet sur backend et frontend.
- Depuis le 2026-11-03, backend et frontend sont en v4.2.0 (v4.1.2 avant) : backend `sha256:d0a387d4…f67`, frontend `sha256:2eeab7f3…761` (digests complets dans `compose.override.yaml`). Version confirmée par les labels d'image (4.2.0, révision du tag `v4.2.0`) ; HTTP 200 en local et sur l'adresse tailnet ; conteneurs healthy. Migration `0073_email_accounts_sort_order_renumber` appliquée au démarrage. Sauvegarde avant mise à jour : `backups/mailflow-20261103-1931.dump` ; retour arrière : `compose.override.yaml.bak-pre-4.2.0-20261103` et ce dump.
- Pile de secours pi5max : backend, frontend et postgres aux mêmes digests 4.2.0 depuis le 2026-11-03, images arm64 effectivement tirées et vérifiées (labels 4.2.0). Redis y est épinglé à un digest différent, `sha256:8da19c73…` (liste multi-arch de `redis:7.4.12-alpine`, `redis_version` 7.4.12 vérifié en arm64) : le digest de m720q `sha256:1cf73a2f…` est un manifeste amd64 seul. Pile restée arrêtée, démarrage non testé ; retour arrière : `compose.override.yaml.bak-pre-4.2.0-20261103` sur pi5max.
- Depuis le 2026-11-03, Redis est en 7.4.12 (`sha256:1cf73a2f…`), correctif du débordement de tampon dans la propagation des PUBLISH de plus de 4 Go ; `redis_version` vérifié dans le conteneur, clés conservées et backend reconnecté après la bascule. PostgreSQL répond en 16.15 (vérifié le 2026-11-03).
- `compose.override.yaml.bak-pre-4.1.1-20261030` contient d'autres digests de backend et de frontend. Ils ne correspondent ni à la configuration active ni à HEAD. Quels digests tournent réellement : non vérifié.
- `compose.gsd-005.candidate.yaml` (ignoré) répète `mem_limit`, `security_opt` et `logging` des quatre services, à l'identique de l'override. Il ne contient pas de clé `image` pour backend et frontend, mais contient celles de postgres et redis, identiques à l'override. Il n'est pas utilisé par `compose.yaml` ni par l'override.

## Sauvegardes

- Script : `backup.sh`. Lancé chaque jour à 03:30 par la crontab de l'utilisateur m720q (`crontab -l`). Journal : `backups/backup.log`, qui reçoit la sortie standard et d'erreur de cette ligne de crontab (`2>&1`).
- Destination : `$HOME/mailflow/backups`, soit `backups/` dans ce dossier.
- Méthode : `docker exec mailflow-postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc'` (format custom). Le fichier est écrit en `.dump.tmp`, vérifié, puis renommé en `mailflow-auto-AAAAMMJJ-HHMM.dump`. `umask 077` : fichiers en 600.
- Rétention (depuis le 2026-11-02) : les 7 plus récents dumps **automatiques** au premier niveau de `backups/` : `mailflow-auto-*.dump` et, pendant la transition, l'ancien format `mailflow-AAAAMMJJ-0330.dump`. Les dumps manuels (`mailflow-AAAAMMJJ-HHMM.dump` hors 03:30, `failback-*`, `pre-failback-*`) ne sont ni comptés ni supprimés. Les sous-dossiers, comme `pre-4.0.5-20261025-211311/`, ne sont pas concernés.
- Taille observée (7 dumps présents au 2026-10-30, `ls -l`) : de 17 321 393 à 18 468 524 octets, soit 17,3 à 18,5 Mo (10^6 octets), ou 16,5 à 17,6 Mio (2^20 octets).
- Vérification du dump : taille non nulle, puis `docker exec -i mailflow-postgres pg_restore --list < "$TMP"` avec au moins une entrée `TABLE DATA`. Un seul chemin utilise les outils du conteneur : aucune dépendance Postgres sur l'hôte, aucune copie ni fichier temporaire dans le conteneur. En cas d'échec : dump `.tmp` retiré, ligne `ECHEC`, code de sortie 1, pas de rotation.
- Tests hors production : `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v`. Faux Docker, HOME temporaire ; succès, permissions 600, rétention de sept dumps automatiques, conservation des manuels et quatre échecs simulés validés. Syntaxe `sh -n` valide. Le passage complet sur la base réelle reste à vérifier au cron.
- Vérification réelle en lecture seule : le dump existant `mailflow-20261102-1159.dump` est accepté par `pg_restore --list` via stdin dans le conteneur (34 entrées `TABLE DATA`). Cela ne prouve pas une restauration.
- Journal : une ligne horodatée `OK …` ou `ECHEC …` par exécution dans `backups/backup.log` (vide à ce jour, dernière écriture du 2026-10-24).
- Restauration : aucune procédure dans le dépôt. Le format `-Fc` se restaure en principe avec `pg_restore` (usage général de PostgreSQL). Restauration : non vérifié.
- Autres lignes crontab (lues avec `crontab -l` le 2026-11-02, contenu des scripts non vérifié) : `backup-to-5max.sh` à 03:45 (remplace `backup-to-nuc.sh`, désactivé le 2026-10-31), `backup-watchdog.sh` à 08:00, `pihole/backup.sh` à 03:20 et `restore-drill-weekly.sh` le dimanche à 04:30.
- Depuis le 2026-10-31 : `backup-to-5max.sh` (03:45) archive aussi ce dossier vers pi5max (`/mnt/ssd/m720q-backups`) et `mailflow-sync.sh` envoie un dump toutes les 10 minutes depuis le 2026-11-03 (voir « Redondance »).
- Dumps hors cadence observés : `mailflow-20261027-2137`, `mailflow-20261028-1414`, `mailflow-20261030-2036`, `mailflow-20261102-1159` (ce dernier est la sauvegarde avant mise à jour 4.1.2). Lancement manuel, non vérifié pour les autres.

## IA (via opencodex, mis à jour le 2026-11-02)

- Configuration : ligne `ai_config` de la table `system_settings` (base `mailflow`, hors dépôt git), fournisseur `api-key`, fonctions `compose` et `summarize` activées. La clé d'API y est chiffrée (`enc:v1:…`), valeur non lue ici.
- Passerelle : opencodex (`~/opencodex`, hub `ocx` sur le port 10100), joint par `baseUrl` = `http://172.17.0.1:18800/ocx/v1`. Chaîne : socat `hermes-gw-relay` (172.17.0.1:18800) → mux `~/ocx-relay/mux.mjs` (:18850) → opencodex `127.0.0.1:10100`.
- Pare-feu : `hermes-relay-guard.service` (unité systemd utilisateur) coupe le TCP 18800 sauf réseaux autorisés. `172.18.0.0/16` (`mailflow_mailflow`) y est ajouté depuis le 2026-11-02 : sans cette règle, les appels du backend expiraient et l'interface affichait « AI request failed ». Sauvegarde : `hermes-relay-guard.service.bak-20261102-mailflow`. Le sous-réseau n'est pas figé dans `compose.yaml` : à revérifier si le réseau Docker est recréé.
- Modèle : `opencode-go/deepseek-v4.1-flash` (avant : `combo/ds41-flash`, combo de bascule OpenDesign → opencode-go). Le backend relit `ai_config` en base à chaque appel.
- Effort de raisonnement : le backend n'envoie aucun effort (`src/services/aiProvider.js` dans l'image). `high` est la valeur par défaut annoncée par opencodex pour ce modèle, mais `usage.jsonl` n'enregistre aucun effort pour ces appels : application réelle de `high` non vérifiée.
- Limite de sécurité : le mux ne vérifie que la présence d'un en-tête `Authorization`, puis joint le listener loopback non authentifié d'opencodex. Constaté le 2026-11-02 avec un faux jeton depuis `mailflow-backend` : `/ocx/v1/models` répond 200 et une requête `gpt-6.1-terra` passe jusqu'au routage du fournisseur (429 de quota, pas de refus d'authentification). La clé `mailflow` et ses `allowedModels` ne s'appliquent donc pas sur ce chemin, et tout conteneur de `172.18.0.0/16` peut utiliser opencodex.
- Contrôles du 2026-11-02 depuis `mailflow-backend` : `testAiProvider()` et `streamChat()` réussissent (environ 1,2 s, réponse « ok » en streaming). Ces appels passent par le code du backend mais pas par l'interface ni par la route HTTP.
- Retour arrière : remettre `apiKeyConfig.model` à `combo/ds41-flash` dans `ai_config` ; restaurer la sauvegarde de `hermes-relay-guard.service`, puis supprimer la règle `172.18.0.0/16` de `INPUT` (le service ne retire pas les règles existantes).

## Redondance sur pi5max (ajouté le 2026-10-31, cadence mise à jour le 2026-11-03)

Principe : actif/passif. m720q sert MailFlow ; pi5max (Orange Pi 5 Max, DietPi, aarch64, alias SSH `pihole`, nœud Tailscale `pihole`, 100.114.54.27) garde une copie prête, **arrêtée**. Ne jamais faire tourner les deux piles en même temps (clients IMAP en double sur les mêmes boîtes).

- **Adresse** : Service Tailscale `svc:mailflow` (TCP 443, HTTPS automatique), défini via l'API le 2026-10-31 (client OAuth temporaire supprimé le jour même, accès vérifié révoqué : HTTP 401). m720q et pi5max portent l'étiquette `tag:mailflow-host` (nécessaire pour héberger un Service ; elles ne sont plus rattachées au compte utilisateur, retirer l'étiquette demande une ré-authentification). Règle d'accès : `autoApprovers.services` pour cette étiquette et un grant `* → svc:mailflow` port 443. L'ancienne règle (tout autorisé) est sauvegardée dans `~/tailscale-admin/acl-2026*.hujson`. Si deux hôtes annoncent le service, le trafic est réparti entre eux : un seul doit l'annoncer.
- **Données** : `~/mailflow-sync.sh` (m720q, cron toutes les 10 minutes depuis le 2026-11-03, journal `~/mailflow-sync.log`) envoie un `pg_dump -Fc` vers `pihole:~/mailflow/backups-hourly/` (lien symbolique vers `/mnt/ssd/mailflow/backups-hourly` sur le NVMe, 120 gardés soit ~20 h, 600). Distinct de `backup.sh` (nocturne, 7 gardés). Perte maximale : environ 10 minutes de réglages et de cache MailFlow (les mails restent sur les serveurs IMAP). Les sessions Redis ne sont pas copiées : reconnexion après bascule.
- **Pile de secours** : `~/mailflow` sur pi5max, restauré depuis l'archive nocturne (compose, override et `.env` identiques à m720q), images épinglées par digest (multi-arch, tirées). Son `compose.override.yaml` a `APP_URL`/`FRONTEND_URL` = `https://mailflow.taild49e80.ts.net` (sauvegarde `.bak-pre-service-20261031`).
- **Bascule** (pi5max) : `~/mailflow/mailflow-failover.sh up [--force] | down | status`. `up` refuse si m720q répond (contrôle par l'IP tailnet 100.66.86.108, car pi5max ne résout pas les noms MagicDNS), restaure le dernier dump dans une base neuve, démarre la pile et annonce `svc:mailflow`.
- **Retour** (m720q) : `~/mailflow-failback.sh back` arrête m720q, arrête front/back sur pi5max, exporte sa base, fait une sauvegarde de sécurité `backups/pre-failback-*.dump`, restaure avec `pg_restore --clean --if-exists --no-owner --single-transaction --exit-on-error`, redémarre m720q, réannonce le Service, puis exécute `down` sur pi5max. `~/mailflow-failback.sh guard` (cron `@reboot`) arrête front/back de m720q et retire l'annonce si pi5max sert MailFlow. Un chevauchement d'environ une minute est possible au redémarrage (Docker relance les conteneurs avant le garde-fou).
- **Alerte** : bloc ajouté dans `/root/surveillance.sh` de pi5max (cron toutes les 15 min, notification téléphone via ntfy quand la liste des problèmes change) : deux essais HTTPS sur `m720q…:10000` espacés de 20 s. Sauvegarde du script : `/root/surveillance.sh.bak-20261031`. Indépendant de m720q (le watchdog `backup-watchdog.sh` de m720q passe par le conteneur hermes de m720q et se tait si m720q tombe).
- **Vérifié le 2026-10-31** : accès à `https://mailflow.taild49e80.ts.net/` confirmé par Alex (fonctionne très bien) ; restauration d'un vrai dump dans `postgres:16-alpine` sur pi5max (34 tables, comme m720q) ; Service joignable depuis le nuc (HTTP 200) ; refus de `up` tant que m720q répond ; envoi des dumps (horaire à l'époque) ; alerte simulée sur mauvaise IP.
- **Vérifié le 2026-11-03** : cadence à la minute validée (exécutions automatiques réussies à 10:14, 10:15, 10:16, 10:17 et 10:19, dumps d'environ 19,9 Mo ; l'échec de syntaxe de 10:18 était transitoire, pendant l'édition du script), puis ramenée à 10 minutes à 10:22 (prochain passage automatique à 10:30) ; rétention de 120 fichiers testée sur un dossier temporaire ; `~/mailflow/backups-hourly` est un lien symbolique vers `/mnt/ssd/mailflow/backups-hourly` (NVMe, 190 Go libres) pour éviter l'usure de la carte SD ; `mailflow-failover.sh` lit toujours le dernier dump via ce lien.
- **Essai isolé du 2026-11-03 (pi5max, 4.2.0)** : dump `mailflow-20261103-1940.dump` restauré sans erreur dans des conteneurs jetables, sur un réseau Docker interne sans accès extérieur, avec des secrets de test : 34 tables, 6 comptes, 14 225 messages ; backend 4.2.0 arm64 sain en 15 s, « schema up to date », aucune erreur de schéma dans ses journaux. Ne couvre ni le vrai `.env`, ni le déchiffrement des comptes, ni IMAP, ni `mailflow-failover.sh`. Conteneurs et réseau supprimés ensuite.
- **Bascule en conditions réelles** : artefacts de bascule présents du 2026-11-01 (`backups/failback-20261101-0940.dump` et `backups/pre-failback-20261101-0940.dump`, créés à 09:40), résultat non documenté (aucun journal ni compte rendu dans le dépôt ; ces fichiers prouvent qu'un `back` a démarré, pas qu'il a abouti). Comportement du Service quand m720q tombe vraiment : non testé.
- **Limite connue** : pi5max n'utilise pas MagicDNS (`CorpDNS` désactivé) et n'atteint pas le Service depuis lui-même (test par nom et par VIP en échec le 2026-10-31).

## Points connus (état au 2026-10-30, mis à jour le 2026-11-02 là où indiqué)

- Pas de dump `mailflow-20261030-0330.dump` (présents : `20261029-0330` et `20261030-2036`). Cause : non vérifiée.
- `backups/backup.log` fait 0 octet, dernière modification le 2026-10-24 à 03:30:01. L'ancienne version de `backup.sh` n'écrivait rien en cas de succès : un journal vide ne prouve ni succès ni échec. La nouvelle version écrit une ligne par exécution (non encore exécutée).
- `backups/pre-4.0.5-20261025-211311/` est hors rétention. Il contient `mailflow.dump` (16,5 Mio, `ls -lh`), `table-counts.json`, `docker-compose.yml`, `docker-compose.override.yml` et un fichier nommé `.env` (contenu non lu). Le dossier est en 700, le fichier `.env` en 600 (contrôlé le 2026-11-02, contenu non lu).
- `backups/ai_config-20261028-182903.json` contient un champ de clé d'API en clair (valeur non reproduite ici, fichier non lu). Il a été passé de 664 à 600 le 2026-11-02. Le fichier reste présent : suppression ou archivage chiffré à décider.
- Les sauvegardes sont dans le dossier du projet, ignoré par git (`backups/` dans `.gitignore`). Une copie hors de ce dossier est faite vers pi5max par `backup-to-5max.sh` (03:45, voir ci-dessous) : contenu exact non vérifié.
- Les dumps contiennent des données de messagerie (commentaire de `backup.sh`, l. 4).

## Points ouverts (décisions hors de ce dépôt)

- Profil `https` : incompatibilité avec `NGINX_TLS=off` (voir « Accès et réseau ») non vérifiée par un test.
- Fichiers `*.bak-*` et candidat à supprimer ou archiver après contrôle.
- `compose.override.yaml` de pi5max est encore du JSON dans un fichier `.yaml` (m720q est passé en YAML).
- En-tête de `compose.yaml` à corriger.
- Pas de `.env.example`.
- Valeur de `TRUST_PROXY_HOPS` à confirmer.
- Échec de `ENCRYPTION_KEY` vide : à décider (échec immédiat ou comportement actuel).
- Passage progressif des anciens dumps `mailflow-*-0330.dump` au nouveau nommage (premier passage réel de `backup.sh` réussi le 2026-11-03 à 03:30, journal OK).
- Cause de l'absence du dump du 2026-10-30 03:30 à identifier.
- Suppression ou archivage chiffré de `backups/ai_config-20261028-182903.json` (permissions déjà en 600).
- Redondance : test réel de bascule et de retour ; alerte « nuc (secours DNS) ne repond plus » préexistante dans la surveillance de pi5max.

## Non vérifié

- Contenu de `.env` et des fichiers `.env.bak-*`.
- Contenu de `backup-to-5max.sh`, `backup-watchdog.sh` et `pihole/backup.sh`.
- Comportement du backend (code absent du dépôt).
- État réel des conteneurs et des volumes.
- Restaurabilité des dumps nocturnes de `backup.sh` (un dump de `mailflow-sync.sh` a été restauré le 2026-11-03, voir « Redondance sur pi5max »).

### Mise à jour 2026-10-31 (après les tests sur Kanban-AO et OpenTodo)
- `mailflow-failover.sh` (pi5max) utilise maintenant `sudo -n tailscale serve` (sans cela, l'annonce échouait : dietpi n'est pas opérateur), attend le certificat HTTPS de l'adresse avant de rendre la main, et son contrôle « m720q répond ? » regarde le code HTTP (< 500). Sauvegarde : `mailflow-failover.sh.bak-20261031b`. Le bloc d'alerte de `/root/surveillance.sh` utilise la même règle.
- `up` et `back` de MailFlow en réel : voir « Bascule en conditions réelles » ci-dessus, résultat non documenté (même méthode que celle validée sur Kanban-AO et OpenTodo, voir `~/RESTORE-RUNBOOK.md`).

## Correctifs bascule du 2026-11-01 (audit + tests de restaurabilité)

- mailflow-failover.sh (pi5max) : verrou flock ; refuse un dump absent, > 26 h ou illisible
  (pg_restore --list via conteneur jetable) AVANT toute destruction ; re-vérifie m720q juste avant
  up -d ; export de sécurité du volume Postgres existant (backups-hourly/pre-up-*.dump, 3 gardés)
  avant down -v ; pg_restore --exit-on-error --single-transaction ; timeouts sur les boucles.
- mailflow-failback.sh (m720q) : guard coupe l'annonce svc:mailflow sans condition au boot puis
  surveille 15 min (échec SSH ≠ standby absent) ; pose le marqueur .standby-active qui suspend
  mailflow-sync.sh ; back valide le dump pi5max avant de couper, recrée la base (dropdb/createdb)
  au lieu de --clean, retire l'annonce pi5max AVANT de ré-annoncer m720q, messages d'échec
  explicites (trap ERR) avec instructions de reprise.
- mailflow-sync.sh : skip si marqueur présent ou pile de secours active sur pi5max ; verrou flock ;
  ConnectTimeout ; validation pg_restore --list ; refuse un dump < 50 % du précédent ; purge des .tmp.
- Sauvegardes des versions précédentes : *.bak-20261101 (m720q) et
  pihole:~/mailflow/mailflow-failover.sh.bak-20261101.
- Vérifié : up refuse quand m720q répond (HTTP 200) ; syntaxe bash validée sur les trois scripts.
- Reste : documenter le résultat de la bascule/retour du 2026-11-01 (artefacts présents, voir TEST-BASCULE.md pour la procédure).


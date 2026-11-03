# MailFlow — Plan de test de bascule m720q → pi5max

Machine primaire : **m720q** (~/mailflow, docker compose) — Service Tailscale : <https://mailflow.taild49e80.ts.net>
Machine de secours : **pi5max** (alias SSH `pihole`, ~/mailflow, dumps toutes les 10 min dans `~/mailflow/backups-hourly/`)

## 0. Rappels de sécurité (à lire avant tout)

- **Ne jamais faire tourner les deux piles en même temps** : deux clients IMAP sur les mêmes boîtes corrompraient les données. La bascule comme le retour arrêtent toujours un côté avant de démarrer l'autre.
- **Perte de données maximale : ~10 min** — la synchro m720q → pi5max (`~/mailflow-sync.sh`) tourne toutes les 10 minutes et conserve 120 dumps (~20 h). Tout ce qui est arrivé depuis le dernier dump (au plus ~10 min) est perdu en cas de bascule.
- **Les sessions Redis ne sont pas copiées** : tous les utilisateurs devront se reconnecter après la bascule ET après le retour.
- **Le certificat HTTPS du Service est préchauffé** par le script pi5max (`tailscale cert`, ~35 s au premier appel), la reprise HTTP est donc rapide.
- Le script pi5max refuse `up` si m720q répond encore (sonde HTTP sur `https://m720q.taild49e80.ts.net:10000/`). `--force` n'est à utiliser qu'après avoir **vérifié** que la pile m720q est bien arrêtée.

## 1. Préconditions

À exécuter sur m720q, avant toute manipulation :

```bash
# 1. Pile m720q saine
cd ~/mailflow && docker compose ps            # postgres/backend/frontend : Up (healthy)
# 2. Dernier dump récent (<= 20 min)
tail -n 1 ~/mailflow-sync.log                 # ligne "... OK mailflow-AAAAMMJJ-HHMM.dump"
# 3. Accès SSH à pi5max
ssh pihole true && echo SSH-OK
# 4. Dumps bien présents côté pi5max
ssh pihole 'ls -1t ~/mailflow/backups-hourly/mailflow-*.dump | head -3'
# 5. Aucune pile MailFlow déjà active sur pi5max
ssh pihole 'docker ps --format "{{.Names}}" | grep mailflow || echo aucun'
# 6. Script de retour présent + garde-fou cron en place
ls -l /home/m720q/mailflow-failback.sh
crontab -l | grep failback                     # ligne @reboot ... guard
# 7. Noter les mappages tailscale serve actuels (pour savoir restaurer quoi en cas d'abort)
tailscale serve status
```

**Relevés à noter avant le test** (pour les vérifications post-retour) :

- Nombre total de messages du compte de test dans l'interface MailFlow (ou via le client IMAP).
- Un e-mail de test envoyé et reçu avant la bascule (preuve du fonctionnement initial).

**Point de contrôle HTTP n°0** (depuis m720q ou n'importe quel poste du tailnet) :

```bash
curl -sk -o /dev/null -w "%{http_code}
" https://mailflow.taild49e80.ts.net/
```

Attendu : `200` (m720q répond).

## 2. Fenêtre conseillée et estimation de coupure

- **Fenêtre** : hors heures d'utilisation (soirée tardive / nuit, ou créneau convenu avec les utilisateurs) ; la synchro passe toutes les 10 minutes, la perte potentielle est donc d'environ 10 min à tout moment. Prévenir les utilisateurs : double reconnexion prévue (Redis).
- **Durée totale du test : ~20 à 30 min.**

| Phase | Coupure HTTP estimée | Détail |
|---|---|---|
| Arrêt m720q | immédiat | serve off + conteneurs stoppés |
| Bascule pi5max | ~2 à 5 min | `down -v`, postgres healthy (~30 s), pg_restore, `up -d`, annonce svc + cert préchauffé (~35 s) |
| Failback | ~3 à 8 min | export pg_dump pi5max, dump de sécurité m720q, pg_restore, healthchecks, serve |
| Perte de données | 0 à ~10 min | selon l'heure du dernier dump |

## 3. Étapes du test

### Étape 1 — Arrêt propre de MailFlow sur m720q

```bash
cd ~/mailflow && docker compose stop frontend backend
tailscale serve --service=svc:mailflow --https=443 off
```

Vérifier que rien ne tourne plus :

```bash
docker compose ps        # frontend/backend : Exited
```

> Remarque : m720q a aussi un mappage **non-Service** sur le port 10000 (`https://m720q.taild49e80.ts.net:10000` → 127.0.0.1:18081). Une fois le backend arrêté, ce mappage répond `502`, ce qui fait REFUSER la bascule par le script pi5max (code 502 = « m720q répond encore »). Si `tailscale serve status` montre encore cette entrée, la retirer :
>
> ```bash
> tailscale serve --https=10000 off
> ```

**Point de contrôle HTTP n°1** :

```bash
curl -sk -o /dev/null -w "%{http_code}
" --max-time 8 https://mailflow.taild49e80.ts.net/
```

Attendu : `000` (échec de connexion). Si une réponse 2xx/4xx apparaît, la pile n'est pas arrêtée — ne pas continuer.

### Étape 2 — Bascule sur pi5max

```bash
ssh pihole '~/mailflow/mailflow-failover.sh up'
```

Sans `--force`, le script doit accepter (m720q ne répond plus). Résultats attendus dans la sortie :

- `Dump utilisé: .../mailflow-AAAAMMJJ-HHMM.dump (<date>)` — **vérifier que l'horodatage correspond au dernier dump connu** ;
- postgres healthy, `docker compose up -d` complet ;
- annonce `svc:mailflow` sans message ATTENTION ;
- préchauffage du certificat (`tailscale cert`) sans erreur.

En cas de `REFUS: m720q répond encore` alors que l'étape 1 est confirmée : contrôler `tailscale serve status` sur m720q (mappage :10000 résiduel → `tailscale serve --https=10000 off`), et seulement si la pile m720q est **prouvée arrêtée** (`docker compose ps` : tout Exited), relancer avec `--force`.

Vérification côté pi5max :

```bash
ssh pihole 'cd ~/mailflow && docker compose ps && sudo -n tailscale serve status'
```

Attendu : `mailflow-postgres`, `mailflow-backend`, `mailflow-frontend` Up (healthy) et l'entrée `svc:mailflow` annoncée.

**Point de contrôle HTTP n°2** :

```bash
curl -sk -o /dev/null -w "%{http_code}
" --max-time 15 https://mailflow.taild49e80.ts.net/
```

Attendu : `200` (réponse rapide grâce au certificat préchauffé).

### Étape 3 — Validation fonctionnelle sur la secours

1. **Connexion réelle** à <https://mailflow.taild49e80.ts.net> avec le compte de test (une reconnexion est normale : sessions Redis non copiées).
2. **Compte d'e-mails** : le nombre de messages doit correspondre au relevé initial **moins** les messages reçus depuis le dernier dump (perte attendue ≤ 10 min).
3. **Test d'écriture** : envoyer un e-mail de test depuis l'interface — il servira de preuve au rapatriement lors du failback.

### Étape 4 — Retour arrière planifié (failback)

Depuis m720q :

```bash
/home/m720q/mailflow-failback.sh back
```

Le script enchaîne : arrêt m720q → arrêt écriture pi5max + export → dump de sécurité `backups/pre-failback-*.dump` → restauration → démarrage backend/frontend avec healthchecks → annonce `svc:mailflow` → arrêt de la pile pi5max. Contrôles pendant l'exécution :

- l'export doit dépasser 1 Mo (le script abandonne sinon) ;
- `docker compose ps` sur m720q : backend et frontend Up (healthy) ;
- `ssh pihole 'cd ~/mailflow && docker compose ps'` : plus aucun conteneur mailflow.

**Point de contrôle HTTP n°3** :

```bash
curl -sk -o /dev/null -w "%{http_code}
" --max-time 15 https://mailflow.taild49e80.ts.net/
```

Attendu : `200`, servi par m720q (certificat déjà en place, pas d'attente).

### Étape 5 — Vérifications post-retour

```bash
# 1. Connexion réelle au compte de test (reconnexion attendue, Redis)
# 2. Compte d'e-mails : >= relevé initial, ET l'e-mail de test envoyé pendant la secours est présent
# 3. Cycle mail réel : envoyer + recevoir un e-mail de test
# 4. Pile et annonce côté m720q
cd ~/mailflow && docker compose ps
tailscale serve status | grep -A1 svc:mailflow
# 5. pi5max bien éteint
ssh pihole 'docker ps --format "{{.Names}}" | grep mailflow || echo aucun'
# 6. La synchro toutes les 10 min repart (au prochain multiple de 10 min)
tail -n 2 ~/mailflow-sync.log     # nouvelle ligne "... OK mailflow-*.dump"
# 7. Garde-fou reboot toujours actif
crontab -l | grep failback
```

## 4. Plan de retour arrière si une étape échoue

- **Échec avant l'étape 2** (bascule pas encore lancée) : rien à rapatrier. Redémarrer m720q :
  ```bash
  cd ~/mailflow && docker compose start backend &&   until [ "$(docker inspect -f '{{.State.Health.Status}}' mailflow-backend)" = healthy ]; do sleep 3; done &&   docker compose start frontend &&   tailscale serve --service=svc:mailflow --https=443 http://127.0.0.1:18081
  ```
  Puis rejouer le point de contrôle HTTP n°0 (attendu `200`).
- **Échec pendant `failover.sh up`** sur pi5max (avant toute écriture utilisateur sur la secours) : la pile m720q est déjà arrêtée, la coupure continue. Ne pas réparer pi5max en urgence : relancer `up` après correction, ou redémarrer m720q comme ci-dessus (les données m720q n'ont pas bougé).
- **Échec pendant `mailflow-failback.sh back`** : le script s'arrête (`set -e`) en laissant m720q ET pi5max arrêtés. Ne pas relancer `back` aveuglément : `STANDBY_RUNNING` ne verra plus le backend pi5max et dira « rien à rapatrier ». Le dump exporté est conservé sur m720q (`~/mailflow/backups/failback-AAAAMMJJ-HHMM.dump`). Restaurer manuellement :
  ```bash
  cd ~/mailflow && docker compose start backend
  docker cp backups/failback-AAAAMMJJ-HHMM.dump mailflow-postgres:/tmp/failback.dump
  docker exec mailflow-postgres sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner --single-transaction --exit-on-error /tmp/failback.dump'
  docker exec mailflow-postgres rm -f /tmp/failback.dump
  docker compose start frontend
  tailscale serve --service=svc:mailflow --https=443 http://127.0.0.1:18081
  ssh pihole '~/mailflow/mailflow-failover.sh down'   # une fois m720q confirmé OK
  ```
  En cas d'échec de cette restauration : `docker compose down -v && docker compose up -d` puis restaurer `backups/pre-failback-*.dump` (état m720q d'avant le retour) — on perd alors uniquement ce qui a été écrit sur la secours.
- **Filet de sécurité global** : dumps toutes les 10 min sur pi5max (~20 h de profondeur), dumps nocturnes `~/mailflow/backups/mailflow-*.dump` sur m720q (7 jours).

## 5. Checklist finale

- [ ] Préconditions 1-7 validées, relevés notés (compte d'e-mails, e-mail initial)
- [ ] Point de contrôle n°0 : `200`
- [ ] m720q arrêté proprement, point de contrôle n°1 : `000`
- [ ] `failover.sh up` : dump du jour utilisé, pas de REFUS, pas d'ATTENTION
- [ ] Point de contrôle n°2 : `200`, réponse rapide (certificat préchauffé)
- [ ] Connexion réelle sur la secours + e-mail de test envoyé
- [ ] `mailflow-failback.sh back` : 6/6 étapes, export > 1 Mo
- [ ] Point de contrôle n°3 : `200`
- [ ] Post-retour : connexion réelle OK, e-mail de secours présent, cycle mail réel OK
- [ ] pi5max éteint, synchro toutes les 10 min relancée, `guard` toujours en cron
- [ ] Restore de :10000 remis sur m720q si retiré à l'étape 1

---

## DNS de secours LAN

**Recommandation** : ajouter **1.1.1.1 (Cloudflare)** comme DNS secondaire sur la box, avec Pi-hole (pi5max) en primaire. Pourquoi : si pi5max est éteint/redémarre pendant la bascule, il ne répond plus aux requêtes DNS du LAN ; sans secondaire, tout le réseau perd la résolution Internet, ce qui aggrave une coupure déjà en cours. Avec un secondaire, les clients basculent sur 1.1.1.1 et continuent de résoudre.

**Limites** : de nombreux clients utilisent le DNS secondaire de façon opportuniste (parfois en parallèle du primaire), ce qui affaiblit le filtrage/blocage Pi-hole ; le comportement exact dépend de chaque équipement. Résoudre via 1.1.1.1 expose les noms consultés à Cloudflare au lieu de Pi-hole.

**Ce que ça ne couvre pas** : les enregistrements locaux de Pi-hole (noms internes, hôtes LAN) resteront indisponibles tant que pi5max est hors service ; la résolution de `mailflow.taild49e80.ts.net` passe par **MagicDNS/Tailscale sur chaque appareil** et est indépendante de la box ; enfin, si la panne porte sur la box ou le lien Internet lui-même, un DNS secondaire ne sert à rien.

# 04. Self-service через Web

## Цель

Показать удобный интерфейс разработчика, который создаёт тот же
`EnvironmentRequest`, что и ручной Git-сценарий.

Portal не создаёт Kubernetes/DVP-ресурсы напрямую. Он определяет владельца по
Dex e-mail и группе, создаёт Git artifact в Gitea и показывает status, который
controller собирает из Git, Argo CD, DVP и AWX.

## Пользователи и профили

| Пользователь | Группа | Профили |
|---|---|---|
| Alice | `practicum-payments-devs` | app-only, app-with-vm |
| Boris | `practicum-analytics-devs` | app-only, app-with-postgres-vm |
| Marina | `practicum-qa-devs` | все профили |

Для полного показа используйте Marina:

```text
marina.volkova.practicum@demo.local
```

Пароль берётся из локального ignored-файла, не из Git.

## 1. Открыть портал

```text
https://selfservice-practicum.d8case.ru
```

Примите предупреждение self-signed certificate и войдите через Dex.

## 2. Объяснить поля

### Профиль стенда

Профиль определяет ресурсы:

- `Контейнерное приложение`: Deployment, Service, Ingress;
- `Приложение + Linux VM`: добавляются DVP disk/VM и AWX bootstrap;
- `Приложение + PostgreSQL VM`: добавляется выбранная версия PostgreSQL.

Пользователь не задаёт произвольные CPU/RAM/image.

### Назначение

Назначение:

- входит в Environment ID;
- сохраняется в Git и аудите;
- не меняет ресурсы профиля.

### TTL

TTL определяет автоматическое время жизни. После истечения controller меняет
desired state в Git, а Argo CD prune удаляет только ресурсы стенда.

## 3. Создать стенд

Для наиболее наглядного показа:

```text
Профиль: Приложение + PostgreSQL VM
PostgreSQL: 18
Назначение: Демонстрация
TTL: 4h
```

Нажмите `Отправить заявку`.

## 4. Читать прогресс

Portal обновляет status каждые 5 секунд. Объясняйте этапы:

1. `Submitted` — request записан в Gitea;
2. `Provisioning` — controller создал desired state;
3. Argo CD становится `Synced/Progressing` и создаёт Deployment, Service,
   Ingress, disk и VM;
4. DVP запускает VM и guest agent;
5. AWX выполняет post-config после `VM Running` и `agentReady=True`;
6. `Ready` — все проверки завершены.

Не отправляйте заявку повторно и не обновляйте страницу вручную, пока portal
показывает `В работе`: результат обновляется автоматически.

## 5. Проверить результат

Portal должен показать:

- Environment ID;
- namespace `practicum-tks`;
- owner и profile;
- PostgreSQL version;
- TTL;
- приложение `ready 1/1`;
- URL;
- VM, IP, CPU/RAM/disk и image;
- AWX job/status;
- готовую команду `d8 v ssh`.

В терминале:

```bash
export NAMESPACE=practicum-tks
export ENV_ID=<скопировать-из-портала>

kubectl get deploy,svc,ingress,vd,vm -n "$NAMESPACE" \
  -l "demo.practicum/environment=${ENV_ID}" -o wide
```

Для профиля PostgreSQL проверьте, что AWX применил выбранную версию внутри VM:

```bash
d8 v ssh "ansible@${ENV_ID}-vm" \
  --namespace "$NAMESPACE" \
  --identity-file /Users/kir/code/ArgoAWXk8sDVPdemo/local/practicum-ssh/id_ed25519 \
  --local-ssh \
  --command 'psql --version; apk info | grep -E "^postgresql" | head -20'
```

Ожидается `psql (PostgreSQL) 18.x` и пакеты `postgresql18`. IP вида
`10.66.x.x` относится к внутренней DVP-сети: для интерактивной сессии
используйте готовую команду `d8 v ssh`, которую показывает portal, а не прямое
подключение к IP.

## 6. Показать Git

В Gitea найдите Environment ID в каталогах:

```text
gitops/self-service/practicum/requests/
gitops/environments/practicum/self-service/generated/
gitops/self-service/practicum/status/
```

Главная мысль:

> Portal не является вторым control plane. Он создаёт Git artifact, а дальше
> работает та же цепочка controller → Argo CD → DVP → AWX.

## 7. Мои стенды

Откройте вкладку `Мои стенды`:

- видны только environments текущего пользователя;
- кнопка `Обновить` читает актуальный Git status;
- доступны удаление VM и полного стенда;
- для выполняющейся операции показывается текущий этап.

При выборе `Удалить стенд` portal выводит Environment ID, владельца и список
ресурсов. Подтвердите действие дважды. Это создаёт `EnvironmentAction`
`delete-environment` в Gitea. Controller архивирует request/action, удаляет
generated desired state, а Argo CD prune удаляет только app, Service, Ingress,
VirtualDisk и VM выбранного environment.

Не используйте `kubectl delete`. `Удалить VM` удаляет только VM и disk, оставляя
приложение; для возврата стенда к чистой демонстрационной точке выбирайте
`Удалить стенд`.

## 8. Проверить cleanup и аудит

После статусов `DeletionRequested` и `Deleting` portal должен показать
`Cleaned`. Проверьте итог в терминале:

```bash
git fetch -q practicum-gitea main

git show "FETCH_HEAD:gitops/self-service/practicum/status/${ENV_ID}.json" |
  jq '{environmentId, state, lastAction, argoCD}'

kubectl get deploy,svc,ingress,vd,vm -n "$NAMESPACE" \
  -l "demo.practicum/environment=${ENV_ID}"

kubectl get application practicum-demo -n "$NAMESPACE" -o wide

git ls-tree -r --name-only FETCH_HEAD | grep "$ENV_ID"
```

Ожидается:

```text
state: Cleaned
lastAction.status: Completed
No resources found
practicum-demo: Synced / Healthy
```

В Git остаются только audit paths: `archive/<environment-id>.yaml`,
`actions-archive/<action-id>.json` и `status/<environment-id>.json`.

## Ожидаемый результат

Пользователь получает готовый временный стенд без доступа на создание
Kubernetes/DVP-объектов и без ручного обращения к администратору. Создание и
удаление сохраняют GitOps audit и не затрагивают namespace `practicum-tks`,
golden images, builder VM и платформенные компоненты.

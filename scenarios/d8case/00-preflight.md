# 00. Подготовка демонстратора

## Цель

До начала показа подтвердить, что выбран правильный кластер, платформа
работает, DNS разрешается, а в Git нет незавершённой операции.

## 1. Репозиторий

```bash
cd /Users/kir/code/ArgoAWXk8sDVPdemo
git status
git remote -v
git fetch practicum-gitea main
git log -1 --oneline practicum-gitea/main
```

Ожидается remote:

```text
practicum-gitea http://gitea-practicum.d8case.ru/practicum/practicum-demo.git
```

Controller коммитит status в `main`, поэтому перед локальными изменениями:

```bash
git pull --rebase practicum-gitea main
```

Force-push запрещён.

## 2. Kubernetes context

```bash
kubectl config current-context
kubectl auth can-i get pods -n practicum-tks
kubectl get project practicum-tks 2>/dev/null || true
kubectl get namespace practicum-tks
```

Ожидаемый context:

```text
practicum-tks-api.d8case.ru
```

## 3. Состояние платформы

```bash
kubectl get application -n practicum-tks practicum-demo

kubectl get deploy -n practicum-tks \
  practicum-gitea \
  argocd-server \
  practicum-awx-web \
  practicum-awx-task \
  practicum-request-controller \
  practicum-self-service-portal \
  practicum-vm-admin-portal
```

Ожидается:

- Application `Synced/Healthy`;
- каждый Deployment имеет `READY 1/1`.

## 4. Состояние DVP

```bash
kubectl get vi,vd,vm -n practicum-tks -o wide
kubectl get cm practicum-golden-image-catalog -n practicum-tks \
  -o jsonpath='{.data.activeGoldenImage}{"\n"}'
```

Ожидается:

- source image `practicum-alpine-base-3-23-v1` — `Ready`;
- golden images `practicum-alpine-golden-3-23-v1` и `v2` — `Ready`;
- active image — `practicum-alpine-golden-3-23-v2`;
- builder VM остановлены.

## 5. Проверка URL

```bash
for host in \
  gitea-practicum.d8case.ru \
  argocd-practicum.d8case.ru \
  awx-practicum.d8case.ru \
  selfservice-practicum.d8case.ru \
  vm-admin-practicum.d8case.ru; do
  printf '%-45s ' "$host"
  getent hosts "$host" 2>/dev/null || dscacheutil -q host -a name "$host"
done
```

Порталы используют self-signed certificate. Браузерное предупреждение можно
принять для демонстрации.

## 6. Активные заявки

```bash
find gitops/self-service/practicum/requests \
  -maxdepth 1 -type f ! -name README.md -print

kubectl get deploy,svc,ingress,vd,vm -n practicum-tks \
  -l demo.practicum/environment
```

Не используйте старый Environment ID из документации. Каждый новый request
получает динамический ID.

## Что сказать аудитории

> Мы сначала подтверждаем context и Application. На общем стенде особенно
> важно не перепутать namespace и не использовать команды старого демо. Все
> сегодняшние действия ограничены DKP Project и namespace `practicum-tks`.


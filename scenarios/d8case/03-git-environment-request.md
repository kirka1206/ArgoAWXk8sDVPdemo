# 03. Self-service через Git и JSON

## Цель

Показать, что разработчик коммитит только декларативную заявку, а controller,
Argo CD, DVP и AWX создают стенд без ручного `kubectl apply`.

Все ресурсы создаются в namespace `practicum-tks`. Новый DKP Project или
namespace для каждой заявки не создаётся.

## Общая блок-схема

```plantuml
@startuml
title Git self-service: от заявки до готового стенда
left to right direction
skinparam shadowing false
skinparam rectangle {
  RoundCorner 8
  BackgroundColor #F8FAFC
  BorderColor #2563EB
}

actor "Разработчик" as Developer
rectangle "Рабочая копия Git\nEnvironmentRequest" as LocalGit
database "Gitea\npracticum/practicum-demo" as Gitea
rectangle "practicum-request-controller" as Controller
rectangle "Generated desired state\nDeployment, Ingress, VirtualDisk, VM" as Generated
rectangle "Argo CD\nApplication practicum-demo" as Argo
rectangle "Kubernetes и DVP\nnamespace practicum-tks" as Platform
rectangle "AWX\npost-configuration и validation" as AWX
database "Git status\nи lifecycle audit" as Status

Developer --> LocalGit : Создаёт request
LocalGit --> Gitea : commit / push
Gitea --> Controller : request доступен в Git
Controller --> Generated : Валидирует профиль\nи генерирует manifests
Controller --> Gitea : Служебный commit
Gitea --> Argo : Webhook / новая revision
Argo --> Platform : Sync desired state
Platform --> Controller : VM и guest agent готовы
Controller --> AWX : Запускает Job Template
AWX --> Platform : Настраивает гостевую ОС
Controller --> Status : Commit статуса Ready\nили Error
Status --> Developer : URL, VM, AWX job, TTL
@enduml
```

## Важное ограничение текущей реализации

Сервис обработки заявок ищет файлы с расширением `.yaml`, но текущая версия
Python-кода читает их содержимое как JSON. Поэтому для этого сценария:

- имя файла должно оканчиваться на `.yaml`;
- содержимое файла должно быть корректным JSON;
- обычный YAML с первой строкой `apiVersion:` использовать нельзя: заявка
  получит статус `Rejected` до создания ресурсов.

Это техническое ограничение текущего демо-стенда. В дальнейшей версии сервиса
следует добавить полноценную поддержку YAML.

## Детальная блок-схема

```plantuml
@startuml
title Git self-service: детальная обработка EnvironmentRequest
top to bottom direction
skinparam shadowing false
skinparam packageStyle rectangle

actor "Разработчик" as Developer

package "Git" {
  file "requests/<environment-id>.yaml\nJSON-содержимое" as Request
  file "generated/<environment-id>/\nresources.yaml" as Generated
  file "status/<environment-id>.json" as Status
  file "actions/<action-id>.json" as Action
}

package "practicum-request-controller" {
  rectangle "Валидация\nowner, group, profile, TTL\ncapacity" as Validation
  rectangle "Рендер профиля\napp-only / app-with-vm /\napp-with-postgres-vm" as Render
  rectangle "Lifecycle\narchive request, remove generated" as Lifecycle
}

package "GitOps runtime" {
  rectangle "Gitea\nmain + webhook" as Gitea
  rectangle "Argo CD\npracticum-demo" as Argo
  rectangle "Kubernetes API" as K8s
  rectangle "DVP\nVirtualDisk + VirtualMachine" as DVP
  rectangle "AWX\nPracticum Environment\nPost-Config" as AWX
}

Developer --> Request : Создаёт и коммитит
Request --> Validation : Controller читает Git
Validation --> Status : Rejected / Queued / Provisioning
Validation --> Render : Заявка разрешена
Render --> Generated : Создаёт desired state
Generated --> Gitea : Controller commit
Gitea --> Argo : Push webhook
Argo --> K8s : Deployment, Service, Ingress
Argo --> DVP : VirtualDisk и VM
DVP --> AWX : VM Running + guest agent ready
AWX --> Status : job, attempts, result
Status --> Gitea : Controller commit

Developer --> Action : Delete / start / stop / restart
Action --> Lifecycle : Controller читает action
Lifecycle --> Generated : Удаляет или меняет desired state
Lifecycle --> Status : Cleaned / ActionFailed
Generated --> Argo : Следующая revision
Argo --> K8s : Prune только ресурсов environment
@enduml
```

## Sequence-диаграмма

```plantuml
@startuml
title Git self-service: создание, настройка и удаление стенда
autonumber

actor "Разработчик" as Developer
participant "Рабочая копия Git" as LocalGit
database "Gitea\npracticum/practicum-demo" as Gitea
participant "practicum-request-controller" as Controller
participant "Gitea webhook" as Webhook
participant "Argo CD\npracticum-demo" as Argo
participant "Kubernetes API" as K8s
participant "DVP" as DVP
participant "AWX" as AWX
participant "Гостевая ОС VM" as Guest

== Создание заявки ==
Developer -> LocalGit: Создаёт EnvironmentRequest\n*.yaml с JSON-содержимым
Developer -> LocalGit: git commit
LocalGit -> Gitea: git push main
Gitea -> Webhook: Push event
Webhook -> Argo: Refresh revision
note right of Argo
Первый commit содержит request,
но ещё не generated manifests.
end note

== Генерация desired state ==
Controller -> Gitea: Читает requests/
Controller -> Controller: Валидирует owner, group,\nprofile, TTL и capacity
alt Заявка отклонена или ждёт очередь
  Controller -> Gitea: Commit status Rejected / Queued
else Заявка разрешена
  Controller -> Gitea: Commit status Provisioning\nи generated manifests
  Gitea -> Webhook: Push event
  Webhook -> Argo: Refresh revision
  Argo -> Gitea: Читает generated desired state
  Argo -> K8s: Создаёт app, Service, Ingress
  Argo -> DVP: Создаёт VirtualDisk и VM
  DVP -> Guest: Запускает VM из activeGoldenImage
  Guest --> Controller: Guest agent готов
  Controller -> AWX: Запускает post-config Job Template
  AWX -> Guest: Ansible configuration и validation
  alt AWX successful
    AWX --> Controller: Job successful
    Controller -> Gitea: Commit status Ready\nURL, VM, AWX job, SSH command
  else AWX failed
    AWX --> Controller: Job failed
    Controller -> AWX: Retry, максимум 3 попытки
    Controller -> Gitea: Commit status Error\nпосле исчерпания retry
  end
end

== Удаление ==
Developer -> LocalGit: Создаёт EnvironmentAction\ndelete-environment
Developer -> LocalGit: git commit / git rebase / git push
LocalGit -> Gitea: Публикует action
Controller -> Gitea: Архивирует request и action,\nудаляет generated desired state
Gitea -> Webhook: Push event
Webhook -> Argo: Refresh revision
Argo -> K8s: Prune ресурсов environment
Argo -> DVP: Удаляет VM и VirtualDisk
Controller -> Gitea: Commit status Cleaned
@enduml
```

## 1. Подготовить переменные

```bash
cd /Users/kir/code/ArgoAWXk8sDVPdemo
git fetch practicum-gitea main
git pull --ff-only practicum-gitea main

export NAMESPACE=practicum-tks
export ENV_ID="practicum-env-marina-demo-$(date +%H%M%S)"
export CREATED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
export REQUEST_FILE="/Users/kir/code/ArgoAWXk8sDVPdemo/gitops/self-service/practicum/requests/${ENV_ID}.yaml"
printf 'Environment ID: %s\nCreated at: %s\nRequest file: %s\n' \
  "$ENV_ID" "$CREATED_AT" "$REQUEST_FILE"
```

Имя должно:

- начинаться с `practicum-env-`;
- содержать только lowercase, цифры и `-`;
- быть не длиннее 63 символов.

## 2. Создать EnvironmentRequest в JSON-формате

Несмотря на расширение `.yaml`, ниже записывается JSON. Не заменяйте фигурные
скобки YAML-отступами.

```bash
cat > "$REQUEST_FILE" <<EOF
{
  "apiVersion": "demo.practicum/v1",
  "kind": "EnvironmentRequest",
  "metadata": {
    "name": "${ENV_ID}"
  },
  "spec": {
    "owner": "marina-volkova-practicum",
    "email": "marina.volkova.practicum@demo.local",
    "groups": ["practicum-qa-devs"],
    "profile": "app-with-vm",
    "purpose": "demo",
    "ttl": "2h",
    "createdAt": "${CREATED_AT}"
  }
}
EOF

jq . "$REQUEST_FILE"
```

Разрешённые профили:

| Profile | Результат |
|---|---|
| `app-only` | Deployment, Service, Ingress |
| `app-with-vm` | приложение и минимальная Linux VM |
| `app-with-postgres-vm` | приложение, VM и PostgreSQL post-config |

Для PostgreSQL добавьте:

```json
"postgresql": {"version": "18"}
```

Поддерживаются версии `16`, `17`, `18`.

## 3. Commit и push

```bash
git add "$REQUEST_FILE"
git commit -m "Request practicum environment ${ENV_ID}"

# Controller также пишет в main. Перед push переносим свой commit
# поверх актуальной истории Gitea и никогда не используем force-push.
git fetch practicum-gitea main
git rebase practicum-gitea/main
git push practicum-gitea main
```

GitHub является копией проекта, но live Argo CD читает Gitea.

Если Gitea отклонил push с `non-fast-forward`, повторите `git fetch`,
`git rebase practicum-gitea/main` и `git push`. При конфликте остановитесь и
разберите конфликт; `git push --force` запрещён.

## 4. Наблюдать Git

В Gitea покажите появление:

```text
gitops/self-service/practicum/requests/<environment-id>.yaml
gitops/environments/practicum/self-service/generated/<environment-id>/
gitops/self-service/practicum/status/<environment-id>.json
```

Controller может создать несколько status-коммитов. Это штатно.

## 5. Наблюдать Argo CD

```bash
while true; do
  clear
  date
  kubectl get application practicum-demo -n "$NAMESPACE" \
    -o custom-columns=NAME:.metadata.name,SYNC:.status.sync.status,HEALTH:.status.health.status,REVISION:.status.sync.revision
  sleep 5
done
```

Остановить просмотр: `Ctrl+C`. В UI Argo CD найдите ресурсы по Environment ID.

## 6. Наблюдать Kubernetes/DVP

```bash
while true; do
  clear
  date
  kubectl get deploy,svc,ingress,vd,vm -n "$NAMESPACE" \
    -l "demo.practicum/environment=${ENV_ID}" \
    --request-timeout=10s
  sleep 5
done
```

Пока сервис обработки заявок не создал generated manifests, команда покажет
`No resources found`. После обработки заявки она начнёт показывать Deployment,
Service, Ingress, VirtualDisk и VirtualMachine. Остановить просмотр: `Ctrl+C`.

Для VM:

```bash
kubectl get vm "${ENV_ID}-vm" -n "$NAMESPACE" -o wide
```

## 7. Наблюдать AWX

В AWX откройте Job Template:

```text
Practicum Environment Post-Config
```

Controller запустит job после готовности VM и guest agent.

## 8. Прочитать итоговый status

```bash
git fetch practicum-gitea main
git show "FETCH_HEAD:gitops/self-service/practicum/status/${ENV_ID}.json" | jq .
```

Сервис обработки заявок создаёт отдельные status-коммиты в Gitea. Для их
просмотра не нужен `git pull --rebase`: он не выполнится при незакоммиченных
изменениях в рабочей копии. `git fetch` получает актуальную версию ветки, а
`git show FETCH_HEAD:...` читает status напрямую из неё, не изменяя файлы на
ноутбуке.

Ожидается:

- `state: Ready`;
- приложение `ready 1/1`;
- VM `Running`;
- IP VM;
- AWX `successful`;
- команда `d8 v ssh`.

## 9. Доступ

```bash
kubectl get ingress "$ENV_ID" -n practicum-tks

d8 v ssh "ansible@${ENV_ID}-vm" \
  --namespace "$NAMESPACE" \
  --identity-file local/practicum-ssh/id_ed25519 \
  --local-ssh
```

## Если ранее отправлен обычный YAML

Не исправляйте уже отклонённую заявку во время показа: она полезна как
диагностический след. Создайте новую заявку с новым `ENV_ID` по шагам выше.
Так аудитория увидит чистый успешный путь, а в Git сохранится причина ошибки
предыдущего запуска.

## Cleanup

Удаляйте стенд через портал пользователя или Victor либо через отдельный
`EnvironmentAction` в Git. Не удаляйте request и generated-каталог вручную во
время демонстрации: lifecycle должен остаться аудитируемым. После action
controller архивирует request/action, удаляет generated desired state, а Argo
CD выполняет prune только ресурсов выбранного Environment ID.

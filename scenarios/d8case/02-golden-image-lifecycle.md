# 02. Управление golden images

## Цель

Показать цепочку:

```text
URL source image в Git
→ Argo CD
→ DVP VirtualImage
→ builder disk и VM
→ AWX prepare/validate/shutdown
→ versioned golden image
→ activeGoldenImage
→ новые tenant VM
```

## Последовательность работы компонентов

Диаграмма показывает полный выпуск новой версии, например `v3`. В текущем
стенде опубликованы и сохранены `v1` и `v2`; `v3` приведена как безопасный
пример следующего выпуска.

Перед любым push в Gitea синхронизируйте рабочую копию с
`practicum-gitea/main`. Это особенно важно для общего demo-репозитория:
controller self-service также пишет в `main` служебные status-коммиты. Никогда
не используйте force-push.

```plantuml
@startuml
title Управление golden image: Git -> Argo CD -> DVP -> AWX -> новые VM

autonumber

actor "Администратор\nплатформы" as Admin
participant "Рабочая копия Git\n/Users/kir/code/ArgoAWXk8sDVPdemo" as LocalGit
database "Gitea\npracticum/practicum-demo" as Gitea
participant "Gitea webhook" as Webhook
participant "Argo CD\nApplication practicum-demo" as Argo
participant "Kubernetes API\nnamespace practicum-tks" as K8s
participant "DVP\nVirtualization controllers" as DVP
database "DVP storage\nStorageClass replicated" as Storage
participant "Builder VM\npracticum-golden-builder-v3-vm" as Builder
participant "Гостевая ОС\nв Builder VM" as GuestOS
participant "AWX\npracticum-awx" as AWX
participant "Сервис обработки заявок\nPython Deployment\npracticum-request-controller" as RequestService
actor "Разработчик\nили портал self-service" as Developer
participant "Новая tenant VM" as TenantVM

== Подготовка исходного образа ==

Admin -> LocalGit: Изменяет manifest исходного образа\nsource-image-v3.yaml\nURL, версия, checksum при необходимости
Admin -> LocalGit: Создаёт manifests builder disk и builder VM v3
Admin -> LocalGit: git add / git commit /\ngit fetch / git rebase / git push
LocalGit -> Gitea: Публикует commit в main

Gitea -> Webhook: Push event
Webhook -> Argo: Уведомление о новой revision
Argo -> Gitea: Читает manifests из commit
Argo -> K8s: Применяет желаемое состояние\nVirtualImage, VirtualDisk, VirtualMachine
K8s -> DVP: Передаёт DVP CRD

DVP -> DVP: Создаёт VirtualImage\npracticum-alpine-base-3-23-v3
DVP -> Storage: Импортирует исходный cloud image\nпо URL из Git
Storage --> DVP: Исходный образ готов
DVP -> Storage: Создаёт builder disk v3
DVP -> Builder: Создаёт и запускает builder VM v3\n1 core, 5%, 512 MiB
Builder -> GuestOS: Загружает ОС из builder disk
GuestOS --> Builder: SSH и guest agent доступны

== Настройка и проверка ОС ==

DVP --> K8s: VM готова к подключению
K8s --> AWX: Событие или запуск workflow\nподготовки golden image
AWX -> Builder: Подключается по SSH
AWX -> GuestOS: prepare-golden-image.yml\nустановка пакетов и конфигураций
AWX -> GuestOS: Очистка временных данных,\nлогов, machine-id и host keys
AWX -> GuestOS: validate-golden-image.yml\nпроверка пакетов, сервисов и конфигурации

alt Validation successful
    AWX -> Builder: Корректно выключает VM
    Builder -> DVP: VM переходит в Stopped
    DVP -> Storage: Фиксирует подготовленный builder disk v3
    DVP -> K8s: Публикует новый versioned VirtualImage\npracticum-alpine-golden-3-23-v3
    K8s --> Argo: Ресурс готов
    Argo --> Admin: Application остаётся Synced/Healthy
else Validation failed
    AWX --> Admin: Workflow Failed,\nлоги и причина доступны в AWX
    note right of AWX
      Образ v3 не назначается активным.
      Версии v1 и v2 остаются без изменений.
    end note
end

== Отдельное назначение активной версии ==

Admin -> LocalGit: Проверяет v3 и согласует выпуск
Admin -> LocalGit: Изменяет файл\n.../golden-images/catalog.yaml
note right of LocalGit
activeGoldenImage:
  practicum-alpine-golden-3-23-v3
end note

Admin -> LocalGit: git commit /\ngit fetch / git rebase / git push
LocalGit -> Gitea: Commit promotion
Gitea -> Webhook: Push event
Webhook -> Argo: Уведомление о новой revision
Argo -> Gitea: Читает catalog.yaml
Argo -> K8s: Обновляет ConfigMap\npracticum-golden-image-catalog
K8s --> Argo: ConfigMap применён
Argo --> Admin: Synced / Healthy

== Использование образа новой заявкой ==

Developer -> RequestService: Создаёт EnvironmentRequest\nчерез портал или Git
RequestService -> K8s: Читает ConfigMap\nactiveGoldenImage
K8s --> RequestService: practicum-alpine-golden-3-23-v3
RequestService -> Gitea: Создаёт generated desired state\nдля tenant environment
Gitea -> Webhook: Push event
Webhook -> Argo: Уведомление о новой revision
Argo -> K8s: Применяет manifests новой tenant VM
K8s -> DVP: Создаёт VirtualDisk и VM
DVP -> Storage: Создаёт диск из golden image v3
DVP -> TenantVM: Запускает новую VM
TenantVM --> Developer: VM создана из v3

== Безопасный rollback ==

opt Если v3 требует отката
    Admin -> LocalGit: Меняет activeGoldenImage обратно на v2
    Admin -> LocalGit: git commit /\ngit fetch / git rebase / git push
    LocalGit -> Gitea: Commit rollback
    Gitea -> Webhook: Push event
    Webhook -> Argo: Уведомление о новой revision
    Argo -> K8s: Возвращает ConfigMap на v2
    note right of K8s
      Меняется только выбор образа
      для будущих VM.

      Уже созданные VM и их диски
      не изменяются.
    end note
end

@enduml
```

## Исходное состояние

```bash
export NAMESPACE=practicum-tks
export APP_NAME=practicum-demo

kubectl get application "$APP_NAME" -n "$NAMESPACE"
kubectl get vi,vd,vm -n "$NAMESPACE" -o wide
```

## 1. Источник образа

В Gitea откройте:

```text
gitops/environments/practicum/golden-images/source-image.yaml
```

Текущий URL:

```text
https://dl-cdn.alpinelinux.org/alpine/v3.23/releases/cloud/generic_alpine-3.23.3-x86_64-bios-cloudinit-r0.qcow2
```

### Альтернативные source images для демонстрации

Для live-показа лучше использовать небольшие cloud images. Самый безопасный
вариант для текущего стенда — Alpine: импорт быстрый, размер небольшой, AWX
playbooks уже адаптированы.

Пример новой версии на той же ветке Alpine:

```yaml
apiVersion: virtualization.deckhouse.io/v1alpha2
kind: VirtualImage
metadata:
  name: practicum-alpine-base-3-23-v2
  namespace: practicum-tks
spec:
  storage: ContainerRegistry
  dataSource:
    type: HTTP
    http:
      url: https://dl-cdn.alpinelinux.org/alpine/v3.23/releases/cloud/generic_alpine-3.23.3-x86_64-bios-cloudinit-r0.qcow2
```

Пример смены minor-линейки Alpine:

```yaml
apiVersion: virtualization.deckhouse.io/v1alpha2
kind: VirtualImage
metadata:
  name: practicum-alpine-base-3-22-v1
  namespace: practicum-tks
spec:
  storage: ContainerRegistry
  dataSource:
    type: HTTP
    http:
      url: https://dl-cdn.alpinelinux.org/alpine/v3.22/releases/cloud/generic_alpine-3.22.2-x86_64-bios-cloudinit-r0.qcow2
```

Более понятный аудитории, но более тяжёлый вариант — Ubuntu cloud image:

```yaml
apiVersion: virtualization.deckhouse.io/v1alpha2
kind: VirtualImage
metadata:
  name: practicum-ubuntu-base-24-04-v1
  namespace: practicum-tks
spec:
  storage: ContainerRegistry
  dataSource:
    type: HTTP
    http:
      url: https://cloud-images.ubuntu.com/noble/current/noble-server-cloudimg-amd64.img
```

Для короткой демонстрации рекомендуется показывать переход:

```text
Alpine 3.22 → Alpine 3.23
```

или:

```text
Alpine 3.23 v1 → Alpine 3.23 v2
```

Ubuntu лучше оставить как архитектурный пример: он крупнее, дольше
импортируется и может потребовать отдельной адаптации AWX playbooks.

Проверка:

```bash
kubectl get vi practicum-alpine-base-3-23-v1 \
  -n "$NAMESPACE" -o wide
```

Что сказать:

> Администратор задаёт URL и версию в Git. DVP импортирует образ, а не
> использует локальный файл с ноутбука.

## 2. Builder v1 и v2

```bash
kubectl get vd \
  practicum-golden-builder-root \
  practicum-golden-builder-v2-root \
  -n "$NAMESPACE" -o wide

kubectl get vm \
  practicum-golden-builder-vm \
  practicum-golden-builder-v2-vm \
  -n "$NAMESPACE" -o wide
```

Ожидается:

- `1 core`, `5%`, `512Mi`;
- VM `Stopped`;
- disks `Ready`, `InUse=False`.

Builder VM не запускаются для обычной демонстрации: golden images v1/v2 уже
опубликованы. Это экономит ресурсы общего стенда.

## 3. AWX pipeline

В AWX откройте успешный golden image workflow и покажите этапы:

1. prepare;
2. customization;
3. validation;
4. shutdown;
5. publication.

Playbooks находятся в:

```text
gitops/awx/playbooks/prepare-golden-image.yml
gitops/awx/playbooks/validate-golden-image.yml
```

## 4. Опубликованные версии

```bash
kubectl get vi \
  practicum-alpine-golden-3-23-v1 \
  practicum-alpine-golden-3-23-v2 \
  -n "$NAMESPACE" -o wide
```

Обе версии должны оставаться `Ready`. Новая версия создаётся новым объектом,
а не изменением data source уже provisioned image/disk.

## 5. Active image

В Gitea откройте:

```text
gitops/environments/practicum/golden-images/catalog.yaml
```

Проверка:

```bash
kubectl get cm practicum-golden-image-catalog -n "$NAMESPACE" \
  -o jsonpath='{.data.activeGoldenImage}{"\n"}'
```

Ожидается:

```text
practicum-alpine-golden-3-23-v2
```

Controller использует это значение при генерации новой tenant VM.

## 6. Как показать выпуск v3

Не изменяйте v1/v2. Для реального выпуска:

1. создать новые `VirtualDisk` и builder VM с суффиксом `v3`;
2. запустить AWX prepare и validation;
3. опубликовать `practicum-alpine-golden-3-23-v3`;
4. отдельным commit изменить `activeGoldenImage`;
5. создать новый environment и показать, что его диск использует v3.

## Rollback

Rollback не удаляет v2. Отдельным Git commit верните:

```yaml
activeGoldenImage: practicum-alpine-golden-3-23-v1
```

Полный пример:

```bash
git fetch practicum-gitea main
git pull --ff-only practicum-gitea main

$EDITOR gitops/environments/practicum/golden-images/catalog.yaml
git diff
git add gitops/environments/practicum/golden-images/catalog.yaml
git commit -m "Rollback active golden image to v1"
git fetch practicum-gitea main
git rebase practicum-gitea/main
git push practicum-gitea main
```

Если push отклонён с `non-fast-forward`, ещё раз выполните `git fetch`,
`git rebase practicum-gitea/main` и `git push`. Force-push запрещён: он может
удалить commit controller с self-service status.

После синхронизации:

```bash
kubectl get cm practicum-golden-image-catalog -n "$NAMESPACE" \
  -o jsonpath='{.data.activeGoldenImage}{"\n"}'
```

Ожидаемо:

```text
practicum-alpine-golden-3-23-v1
```

Это влияет только на новые VM. Уже созданные VM сохраняют исходный диск.
Такой rollback не пересобирает и не меняет существующие VirtualDisk: это
важное свойство безопасной эксплуатации. Если нужно перевести уже работающий
стенд на другой образ, создавайте новый environment или отдельный controlled
recreate/restore flow.

## Нельзя делать

```bash
# Не выполнять:
kubectl patch vd <provisioned-disk> ...
kubectl delete vi practicum-alpine-golden-3-23-v1 ...
```

У provisioned `VirtualDisk` нельзя менять data source. Для новой версии нужен
новый versioned объект.

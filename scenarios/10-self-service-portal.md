# 10. Self-Service Portal

## Цель

Показать, как разработчик создаёт тестовый стенд через web UI, но GitOps остаётся source of truth.

## Исходное состояние

- Portal доступен по `https://selfservice-awx.d8.kir.lab`.
- Доступ закрыт через DKP `DexAuthenticator`.
- В Dex созданы demo-пользователи и группы.
- Backend имеет Kubernetes Secret с учёткой Gitea.
- Argo CD синхронизирует `gitops/environments/prod`.

## Что делает пользователь

1. Открывает `https://selfservice-awx.d8.kir.lab`.
2. Логинится через Dex.
3. Выбирает профиль стенда:
   - `app-only`;
   - `app-with-vm`;
   - `app-with-postgres-vm`.
4. Выбирает purpose и TTL.
5. Нажимает `Создать стенд`.
6. Ждёт статуса на странице.

## Что объяснить на форме

Профиль стенда — это не свободная форма заказа ресурсов, а заранее утверждённый шаблон платформенной команды.

- `app-only`: создаёт только namespace, RBAC, квоты, demo-app, service и ingress.
- `app-with-vm`: добавляет минимальную DVP VM из утверждённого `ClusterVirtualImage`.
- `app-with-postgres-vm`: добавляет VM как цель для PostgreSQL post-configuration через AWX.

Purpose нужен не Kubernetes, а людям и процессу:

- помогает аудиторам понять, зачем создан стенд;
- попадает в GitOps request и labels/annotations;
- может использоваться будущей cleanup/policy automation.

## Что делает система

Portal не создаёт Kubernetes-ресурсы напрямую. Он создаёт Git artifacts в Gitea:

```text
gitops/self-service/requests/<name>.yaml
gitops/self-service/generated/<name>/
```

После этого Argo CD применяет generated manifests.

## Что показывать в Argo CD

- Application `demo-platform`.
- Новый namespace как managed resource.
- Generated Deployment, Service, Ingress.
- DVP `VirtualDisk` и `VirtualMachine`, если выбран VM-профиль.

## Что показывать в AWX

Для VM-профилей объяснить, что после создания VM AWX выполняет post-configuration:

- bootstrap ОС;
- установка пакетов;
- настройка `qemu-guest-agent`;
- validation.

В текущей реализации portal создаёт инфраструктуру и VM, а AWX post-config остаётся отдельным демонстрационным шагом.

## Проверка через kubectl

```bash
kubectl get deploy,svc,ingress -n self-service-portal
kubectl get dexauthenticator -n self-service-portal
kubectl get certificate -n self-service-portal self-service-portal
kubectl get application -n argocd demo-platform
kubectl get ns | grep dev-
kubectl get deploy,svc,ingress,vd,vm -n <generated-namespace>
```

## Ожидаемый результат

- Пользователь видит только профили, разрешённые его группе.
- Имя стенда генерируется автоматически.
- В Gitea появляется request и generated manifests.
- Argo CD создаёт Kubernetes/DVP ресурсы.
- Portal показывает namespace, профиль, purpose, TTL, квоты, app параметры, service, ingress, VM/disk параметры и Git paths.

## Rollback

Удалить generated каталог и request из Git, затем дождаться Argo CD prune:

```bash
git rm -r gitops/self-service/generated/<generated-namespace>
git rm gitops/self-service/requests/<generated-namespace>.yaml
git commit -m "Remove self-service environment <generated-namespace>"
git push dkp-gitea main
```

## Пояснение для демонстратора

На этом шаге важно подчеркнуть, что UI не заменяет GitOps. Он только делает developer experience удобнее: пользователь выбирает разрешённые параметры, а система превращает это в Git commit. Вся инфраструктура по-прежнему проходит через Git, Argo CD и аудитируемую историю изменений.

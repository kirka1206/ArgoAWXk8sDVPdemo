# Справочник действующего стенда d8case.ru

Этот раздел содержит актуальные параметры стенда `practicum-tks`.

Пошаговые демонстрации:

```text
scenarios/d8case/README.md
```

## Идентификаторы

| Параметр | Значение |
|---|---|
| Kubernetes context | `practicum-tks-api.d8case.ru` |
| DKP Project | `practicum-tks` |
| Namespace | `practicum-tks` |
| Argo CD Application | `practicum-demo` |
| Gitea repository | `practicum/practicum-demo` |
| StorageClass | `replicated` |
| VirtualMachineClass | `generic` |
| Ingress IP | `192.168.2.31` |

## URL

| Сервис | URL |
|---|---|
| Gitea | `http://gitea-practicum.d8case.ru` |
| Argo CD | `http://argocd-practicum.d8case.ru` |
| AWX | `http://awx-practicum.d8case.ru` |
| Portal разработчика | `https://selfservice-practicum.d8case.ru` |
| Portal Victor | `https://vm-admin-practicum.d8case.ru` |

## Платформенные объекты

```text
Deployment/practicum-gitea
Deployment/argocd-server
Deployment/practicum-awx-web
Deployment/practicum-awx-task
Deployment/practicum-request-controller
Deployment/practicum-self-service-portal
Deployment/practicum-vm-admin-portal
```

## Golden images

```text
VirtualImage/practicum-alpine-base-3-23-v1
VirtualImage/practicum-alpine-golden-3-23-v1
VirtualImage/practicum-alpine-golden-3-23-v2
VirtualDisk/practicum-golden-builder-root
VirtualDisk/practicum-golden-builder-v2-root
VirtualMachine/practicum-golden-builder-vm
VirtualMachine/practicum-golden-builder-v2-vm
ConfigMap/practicum-golden-image-catalog
```

Active image читается командой:

```bash
kubectl get cm practicum-golden-image-catalog -n practicum-tks \
  -o jsonpath='{.data.activeGoldenImage}{"\n"}'
```

## Tenant environment

Environment ID всегда динамический:

```text
practicum-env-<owner>-<purpose>-<suffix>
```

Не копируйте ID из старого протокола демонстрации. Получайте его из portal,
Git request или labels:

```bash
kubectl get deploy -n practicum-tks \
  -l demo.practicum/environment \
  -o custom-columns='ENV:.metadata.labels.demo\.practicum/environment,OWNER:.metadata.labels.demo\.practicum/owner,READY:.status.readyReplicas'
```

Объекты environment:

```text
Deployment/<environment-id>
Service/<environment-id>
Ingress/<environment-id>
VirtualDisk/<environment-id>-root
VirtualMachine/<environment-id>-vm
```

VM отсутствует у профиля `app-only`.

## Пользователи

| Пользователь | Группа | Назначение |
|---|---|---|
| Alice | `practicum-payments-devs` | app-only, app-with-vm |
| Boris | `practicum-analytics-devs` | app-only, PostgreSQL VM |
| Marina | `practicum-qa-devs` | все developer profiles |
| Victor | `practicum-vm-operators` | lifecycle tenant environments |

Пароли не хранятся в Git.

## Source of truth

```text
gitops/environments/practicum/
gitops/self-service/practicum/requests/
gitops/self-service/practicum/actions/
gitops/self-service/practicum/status/
```

## Историческая документация

Упоминания следующих значений относятся к предыдущему стенду:

```text
d8.kir.lab
demo-prod
demo-platform
ansible-os-pods
postgres-vm
golden-builder-vm
```

Для текущего стенда заменять их механически нельзя: архитектура и набор
сценариев изменились. Используйте материалы `scenarios/d8case/`.


# Self-service портал с Dex/OIDC

Этот вариант показывает developer-facing портал, размещённый в DKP-кластере.

## Адрес

```text
https://selfservice-practicum.d8case.ru
```

Если DNS не настроен, добавьте на рабочей машине:

```text
192.168.2.31 selfservice-practicum.d8case.ru
```

## Архитектура

```mermaid
flowchart LR
  Dev["Разработчик"] --> Ingress["Ingress selfservice-practicum.d8case.ru"]
  Ingress --> DexAuth["DexAuthenticator"]
  DexAuth --> Dex["Dex / OIDC"]
  Ingress --> Portal["Self-service portal"]
  Portal --> Gitea["Gitea API"]
  Gitea --> Git["GitOps repo"]
  Git --> Argo["Argo CD"]
  Argo --> K8s["Namespace, app, ingress, DVP VM"]
  Portal --> Status["Kubernetes status API"]
```

## Пользователи и группы

На стенде practicum созданы три пользователя:

| Пользователь | E-mail | Группа | Доступные профили |
| --- | --- | --- | --- |
| `alice-koroleva-practicum` | `alice.koroleva.practicum@demo.local` | `practicum-payments-devs` | `app-only`, `app-with-vm` |
| `boris-smirnov-practicum` | `boris.smirnov.practicum@demo.local` | `practicum-analytics-devs` | `app-only`, `app-with-postgres-vm` |
| `marina-volkova-practicum` | `marina.volkova.practicum@demo.local` | `practicum-qa-devs` | все профили |

Рабочие пароли не хранятся в Git. Для текущего стенда они сохранены локально в
ignored-файле `local/practicum-demo-users.env`.

Кнопка `Выйти` в шапке открывает `/logout`. Этот endpoint создаёт
`DexAuthenticator`: он завершает текущую Dex-сессию и позволяет войти под другим
демонстрационным пользователем.

## Как работает заявка

1. Пользователь входит через Dex.
2. Portal получает `X-Auth-Request-User`, `X-Auth-Request-Email`, `X-Auth-Request-Groups`.
3. Пользователь выбирает только разрешённый профиль, purpose, TTL и образ приложения.
4. Имя стенда генерируется автоматически:

```text
dev-<user>-<purpose>-<short-id>
```

5. Backend создаёт в Gitea только `EnvironmentRequest`:

```text
gitops/self-service/practicum/requests/<name>.yaml
```

6. Request controller валидирует заявку и создаёт generated manifests.
7. Argo CD применяет generated manifests в namespace `practicum-tks`.
8. Portal читает status-файл, сформированный controller.

## Что показывает UI

Для каждого профиля портал показывает:

- человеческое описание назначения профиля;
- список создаваемых ресурсов;
- квоты namespace;
- характеристики приложения;
- характеристики VM, если профиль создаёт DVP VM;
- роль AWX post-configuration для VM-профилей.

Назначение стенда тоже описывается явно:

| Purpose | Что означает |
| --- | --- |
| `feature` | Проверка новой функциональности в изолированном namespace. |
| `bugfix` | Воспроизведение дефекта и проверка исправления. |
| `loadtest` | Короткий нагрузочный или ресурсный тест в рамках квот. |
| `demo` | Стенд для показа заказчику, команде или архитектурной аудитории. |

После отправки заявки portal показывает:

- имя заявки;
- имя namespace и его phase;
- owner;
- профиль и purpose;
- TTL;
- квоты;
- параметры `Deployment/demo-app`;
- `Service` и `Ingress`;
- параметры `VirtualDisk` и `VirtualMachine`, если VM создаётся;
- пути GitOps artifacts в Gitea;
- URL приложения.

## Важное ограничение демо

В текущей реализации portal пишет сразу в `main` репозитория Gitea. Это удобно для живого демо.

Production-like вариант должен создавать branch/PR, запускать policy validation, после чего выполнять merge.

## Проверка

```bash
kubectl get dexauthenticator -n practicum-tks selfservice-practicum
kubectl get certificate -n practicum-tks selfservice-practicum
kubectl get deploy,svc,ingress -n practicum-tks
kubectl get users.deckhouse.io \
  alice-koroleva-practicum boris-smirnov-practicum marina-volkova-practicum
kubectl get groups.deckhouse.io \
  practicum-payments-devs practicum-analytics-devs practicum-qa-devs
```

После создания стенда через UI:

```bash
kubectl get deploy,svc,ingress,vd,vm -n practicum-tks \
  -l demo.practicum/environment=<environment-id>
kubectl get application -n practicum-tks practicum-demo
```

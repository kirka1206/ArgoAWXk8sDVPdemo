# Self-service портал с Dex/OIDC

Этот вариант показывает developer-facing портал, размещённый в DKP-кластере.

## Адрес

```text
https://selfservice-awx.d8.kir.lab
```

Если DNS не настроен, добавьте на рабочей машине:

```text
10.77.77.208 selfservice-awx.d8.kir.lab
```

## Архитектура

```mermaid
flowchart LR
  Dev["Разработчик"] --> Ingress["Ingress selfservice-awx.d8.kir.lab"]
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

В демо созданы три пользователя:

| Пользователь | E-mail | Группа | Доступные профили |
| --- | --- | --- | --- |
| `alice-koroleva` | `alice.koroleva@demo.local` | `payments-devs` | `app-only`, `app-with-vm` |
| `boris-smirnov` | `boris.smirnov@demo.local` | `analytics-devs` | `app-only`, `app-with-postgres-vm` |
| `marina-volkova` | `marina.volkova@demo.local` | `qa-devs` | все профили |

Рабочие пароли не хранятся в Git. Для текущего стенда они сохранены локально в `local/self-service-demo-users.md`.

## Как работает заявка

1. Пользователь входит через Dex.
2. Portal получает `X-Auth-Request-User`, `X-Auth-Request-Email`, `X-Auth-Request-Groups`.
3. Пользователь выбирает только разрешённый профиль, purpose, TTL и образ приложения.
4. Имя стенда генерируется автоматически:

```text
dev-<user>-<purpose>-<short-id>
```

5. Backend создаёт в Gitea:

```text
gitops/self-service/requests/<name>.yaml
gitops/self-service/generated/<name>/
```

6. Argo CD применяет generated manifests.
7. Portal читает статус namespace, deployment, ingress и VM через Kubernetes API.

## Важное ограничение демо

В текущей реализации portal пишет сразу в `main` репозитория Gitea. Это удобно для живого демо.

Production-like вариант должен создавать branch/PR, запускать policy validation, после чего выполнять merge.

## Проверка

```bash
kubectl get dexauthenticator -n self-service-portal
kubectl get certificate -n self-service-portal self-service-portal
kubectl get deploy,svc,ingress -n self-service-portal
kubectl get users.deckhouse.io alice-koroleva boris-smirnov marina-volkova
kubectl get groups.deckhouse.io payments-devs analytics-devs qa-devs
```

После создания стенда через UI:

```bash
kubectl get ns | grep dev-
kubectl get deploy,svc,ingress,vd,vm -n <generated-namespace>
kubectl get application -n argocd demo-platform
```

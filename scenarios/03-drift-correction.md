# 03. Drift Correction

## Цель

Показать self-healing и устранение configuration drift.

## Исходное состояние

- В Git для `demo-app` задано ожидаемое количество реплик.
- В ArgoCD Application `demo-platform` включен `selfHeal: true`.

## Что меняем в Git

В Git ничего не меняем. Специально ломаем live-состояние в Kubernetes:

```bash
kubectl scale deployment demo-app --replicas=10 -n demo-prod
```

## Пошаговое выполнение

```bash
kubectl get deploy demo-app -n demo-prod
kubectl scale deployment demo-app --replicas=10 -n demo-prod
kubectl get deploy demo-app -n demo-prod
argocd app get demo-platform
kubectl get deploy demo-app -n demo-prod
```

## Что показывать в ArgoCD

- Временный `OutOfSync` или diff по `replicas`.
- Автоматический self-heal.
- Возврат в `Synced/Healthy`.

## Что показывать в AWX

AWX не участвует. Это чистый GitOps-сценарий про контроль desired state на Kubernetes API.

## Проверка через kubectl

```bash
kubectl get deployment demo-app -n demo-prod
kubectl get pods -n demo-prod -l app=demo-app
```

## Ожидаемый результат

- Ручное изменение откатилось.
- `replicas` снова равно значению из Git.
- ArgoCD показывает `Synced/Healthy`.

## Rollback

Rollback не нужен: Git не менялся. Если self-heal отключен, выполните ручной sync:

```bash
argocd app sync demo-platform
```

## Пояснение для демонстратора

Это сильный момент для архитектурной аудитории: Git остаётся источником истины даже если кто-то обошел процесс и поменял кластер вручную. ArgoCD обнаруживает расхождение и возвращает систему в описанное состояние.

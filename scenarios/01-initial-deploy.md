# 01. Initial Deploy

## Цель

Показать первичное развёртывание приложения, инфраструктурных объектов и базовой VM-модели из Git.

## Исходное состояние

- Репозиторий подключен к ArgoCD Application `demo-platform`.
- В кластере есть ArgoCD и доступ к Git-репозиторию.
- Для DVP VM используется адаптируемый шаблон `gitops/infrastructure/dvp/postgres-vm.template.yaml`.

## Что меняем в Git

Добавляем или обновляем initial manifests:

- `gitops/environments/prod/namespace.yaml`
- `gitops/environments/prod/rbac.yaml`
- `gitops/environments/prod/demo-app.yaml`
- `gitops/environments/prod/monitoring.yaml`
- `gitops/environments/prod/values.yaml`
- `gitops/infrastructure/dvp/postgres-vm.template.yaml`

## Пошаговое выполнение

```bash
argocd app get demo-platform
git add .
git commit -m "Initial demo environment"
git push
argocd app get demo-platform
kubectl get ns demo-prod
kubectl get deploy,svc,ingress -n demo-prod
kubectl get vm -n demo-prod
kubectl get events -n demo-prod --sort-by=.lastTimestamp
```

Если DVP CRD ещё не адаптирован, команда `kubectl get vm` может быть неприменима. В этом случае покажите VM-шаблон в Git и явно проговорите, что он заменяется на фактический CRD платформы.

## Что показывать в ArgoCD

- Application `demo-platform`.
- Status `Synced` и `Healthy`.
- Resource tree: namespace, RBAC, Deployment, Service, Ingress, monitoring placeholder.
- Sync waves: сначала базовые объекты, затем приложение и monitoring.

## Что показывать в AWX

На этом сценарии AWX ещё не является главным действующим лицом. Достаточно показать, что playbooks и hooks уже лежат в Git и будут использованы на следующих шагах.

## Проверка через kubectl

```bash
kubectl get ns demo-prod
kubectl get deploy demo-app -n demo-prod
kubectl get svc,ingress -n demo-prod
kubectl get configmap demo-monitoring-rules -n demo-prod
```

## Ожидаемый результат

- ArgoCD Application находится в состоянии `Synced/Healthy`.
- `demo-app` запущен.
- Ingress и Service созданы.
- Все изменения пришли из Git, без ручного `kubectl apply`.

## Rollback

```bash
git revert HEAD
git push
argocd app get demo-platform
```

## Пояснение для демонстратора

На этом шаге важно подчеркнуть, что оператор не меняет инфраструктуру напрямую. Он меняет декларативное описание в Git, после чего ArgoCD приводит кластер к требуемому состоянию. Это снижает риск ручных ошибок и делает изменения воспроизводимыми.

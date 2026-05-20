# 02. Scale Application

## Цель

Показать масштабирование приложения через изменение Git, а не через ручную команду `kubectl scale`.

## Исходное состояние

- `demo-platform` находится в `Synced/Healthy`.
- В `gitops/environments/prod/values.yaml` указано `app.replicas: 2`.
- В live manifest `gitops/environments/prod/demo-app.yaml` у Deployment указано `replicas: 2`.

## Что меняем в Git

Файл:

```text
gitops/environments/prod/values.yaml
```

Было:

```yaml
app:
  replicas: 2
```

Стало:

```yaml
app:
  replicas: 4
```

Для текущего kustomize-примера также измените `spec.replicas` в `gitops/environments/prod/demo-app.yaml` с `2` на `4`.

## Пошаговое выполнение

```bash
git diff
git add gitops/environments/prod/values.yaml gitops/environments/prod/demo-app.yaml
git commit -m "Scale demo app to 4 replicas"
git push
argocd app get demo-platform
kubectl get deploy demo-app -n demo-prod
kubectl get pods -n demo-prod -l app=demo-app
```

## Что показывать в ArgoCD

- Diff по Deployment `demo-app`.
- Автоматическую синхронизацию.
- Переход Application обратно в `Synced/Healthy`.

## Что показывать в AWX

AWX здесь не запускается. Этот сценарий специально показывает границу ответственности: ArgoCD меняет Kubernetes workload, AWX нужен для процедурной настройки ОС или VM.

## Проверка через kubectl

```bash
kubectl get deploy demo-app -n demo-prod
kubectl get pods -n demo-prod -l app=demo-app
```

## Ожидаемый результат

- `replicas = 4`.
- Количество pod увеличилось.
- Ручных изменений в Kubernetes не было.

## Rollback

```bash
git revert HEAD
git push
argocd app get demo-platform
kubectl get deploy demo-app -n demo-prod
```

## Пояснение для демонстратора

Здесь стоит проговорить, что масштабирование становится обычным изменением в Git. Это удобно для production-процессов: есть review, история изменений, понятный rollback и одинаковый механизм доставки для приложений и инфраструктуры.

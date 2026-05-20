# 06. Broken Release And Rollback

## Цель

Показать безопасный rollback через Git.

## Исходное состояние

- `demo-app` работает с образом `nginx:1.27`.
- ArgoCD Application `demo-platform` находится в `Synced/Healthy`.

## Что меняем в Git

Файл:

```text
gitops/environments/prod/values.yaml
```

Было:

```yaml
app:
  image: nginx:1.27
```

Стало:

```yaml
app:
  image: nginx:broken-demo-tag
```

Для текущего kustomize-примера также измените image в `gitops/environments/prod/demo-app.yaml`.

## Пошаговое выполнение

```bash
git add gitops/environments/prod/values.yaml gitops/environments/prod/demo-app.yaml
git commit -m "Deploy broken image for rollback demo"
git push
argocd app get demo-platform
kubectl get pods -n demo-prod
kubectl describe pod -n demo-prod -l app=demo-app
git revert HEAD
git push
argocd app get demo-platform
kubectl get pods -n demo-prod
```

## Что показывать в ArgoCD

- Degraded или Progressing состояние.
- Diff с несуществующим image tag.
- Возврат в Healthy после `git revert`.

## Что показывать в AWX

AWX в этом сценарии не нужен. Это rollback приложения через GitOps.

## Проверка через kubectl

```bash
kubectl get pods -n demo-prod
kubectl describe pod -n demo-prod -l app=demo-app
```

## Ожидаемый результат

- ArgoCD показывает `Degraded` или `Progressing`.
- Kubernetes показывает `ImagePullBackOff`.
- После `git revert` приложение возвращается в `Healthy`.

## Rollback

Основной rollback и есть часть сценария:

```bash
git revert HEAD
git push
```

## Пояснение для демонстратора

Здесь полезно подчеркнуть, что ошибка не скрывается. Она видна в ArgoCD и Kubernetes events, а восстановление выполняется тем же процессом, что и доставка: через Git. История сохраняется, поэтому понятно, кто и когда изменил release.

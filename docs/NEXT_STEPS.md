# Следующие шаги

## Перед демонстрацией

1. Создать DNS-записи для `gitea-practicum.d8case.ru`,
   `argocd-practicum.d8case.ru`, `awx-practicum.d8case.ru` и
   `selfservice-practicum.d8case.ru` на `192.168.2.31`.
2. Заменить self-signed Certificate portal на доверенный issuer.
3. Проверить вход Alice, Boris и Marina через реальный Dex UI.
4. Выполнить сценарий `scenarios/11-practicum-end-to-end.md`.
5. После bootstrap заменить временный `SuperAdmin` пользователя
   `practicum-tks@demo.local` на минимально необходимые права.

## Улучшения

1. Перевести Gitea automation с прямых commit в `main` на branch/PR.
2. Объединять generated-файлы и kustomization в один Git commit через Git tree
   API или отдельный Git worker.
3. Добавить admission/policy проверку EnvironmentRequest в CI.
4. Хранить runtime credentials через External Secrets/Vault.
5. Добавить Prometheus-метрики controller: queued, active, failed, cleanup.
6. Добавить отдельный retry/backoff status для временных ошибок Gitea/AWX.
7. После демо решить, сохранять ли builder disks; versioned VirtualImage
   удалять или изменять нельзя.

## Полезные команды

```bash
kubectl get application -n practicum-tks practicum-demo
kubectl get vi,vd,vm -n practicum-tks -o wide
kubectl get deploy,svc,ingress -n practicum-tks
kubectl logs -n practicum-tks deploy/practicum-request-controller
kubectl get dexauthenticator,certificate -n practicum-tks
```

# Self-service стенды

Self-service сценарий показывает, как разработчик может запросить временный стенд из approved catalog без ручного обращения к администратору.

## Принцип

Web UI и YAML request не создают ресурсы напрямую. Они создают Git artifact:

```text
gitops/self-service/requests/<request-name>.yaml
```

После review/merge automation генерирует manifests, Argo CD применяет их, AWX выполняет post-configuration.

## Почему это безопаснее прямого UI в кластер

- разработчик выбирает только разрешённый profile;
- CPU/RAM/image/TTL ограничены catalog'ом;
- DVP VM создаётся из утверждённого `ClusterVirtualImage`, доступного tenant namespace;
- все изменения проходят через Git;
- rollback и cleanup делаются через Git;
- реальные credentials не хранятся в Git.

## Web UI

Открыть:

```bash
open self-service-ui/index.html
```

UI генерирует:

- `EnvironmentRequest` YAML;
- команды для branch/commit/push;
- список ресурсов, которые будут созданы после merge.

## GitOps/YAML путь

Этот вариант нужен, чтобы показать чистую GitOps-модель без web portal.

Разработчик создаёт YAML-заявку:

```text
gitops/self-service/requests/<request-name>.yaml
```

Пример:

```yaml
apiVersion: demo.platform/v1
kind: EnvironmentRequest
metadata:
  name: dev-alice-yaml-demo
spec:
  owner: alice-koroleva
  email: alice.koroleva@demo.local
  groups:
    - payments-devs
  profile: app-with-vm
  purpose: demo
  ttl: 2h
  access:
    exposeIngress: true
    sshToVm: false
  software:
    appImage: nginx:1.27
  vm:
    image: alpine-base-3-23-v1
    imageKind: ClusterVirtualImage
```

После commit/push automation должна сгенерировать:

```text
gitops/self-service/generated/<request-name>/
```

В текущем демо generated manifests могут быть подготовлены заранее или созданы portal/backend'ом. Production-like следующий шаг - отдельный controller/CI, который валидирует `EnvironmentRequest` и генерирует manifests автоматически.

Проверка:

```bash
kubectl get application -n argocd demo-platform
kubectl get ns <request-name>
kubectl get deploy,svc,ingress -n <request-name>
kubectl get vd,vm -n <request-name>
```

## Production evolution

Дальше этот сценарий можно развивать:

- backend, который создаёт branch и PR в Gitea/GitHub;
- CI validation request'ов;
- генератор manifests;
- TTL cleanup;
- интеграция с Vault/External Secrets;
- status page для разработчика.

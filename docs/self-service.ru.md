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

## Production evolution

Дальше этот сценарий можно развивать:

- backend, который создаёт branch и PR в Gitea/GitHub;
- CI validation request'ов;
- генератор manifests;
- TTL cleanup;
- интеграция с Vault/External Secrets;
- status page для разработчика.

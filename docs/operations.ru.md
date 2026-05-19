# Операционная памятка

## Запуск стенда

```bash
./scripts/bootstrap.sh
```

Скрипт устанавливает и настраивает:

- Gitea;
- Argo CD;
- AWX;
- demo Linux pod'ы;
- AWX inventory, project, credentials, execution environment и job template.

## Повторно открыть интерфейсы

Если port-forward'ы были остановлены:

```bash
./scripts/port-forward.sh
```

Интерфейсы:

- Gitea: `http://localhost:3001`
- Argo CD: `http://localhost:3000`
- AWX: `http://localhost:3002`

## Запуск демонстрационного job

```bash
./scripts/run-demo-job.sh
```

Скрипт:

1. находит AWX job template `Configure OS pods`;
2. запускает job;
3. ждет финальный статус;
4. выводит последние строки stdout;
5. проверяет marker-файлы внутри pod'ов.

## Проверка состояния

```bash
kubectl get application -n argocd ansible-os-pods
kubectl get pods -n gitea
kubectl get pods -n argocd
kubectl get pods -n awx
kubectl get pods -n demo-os
```

## Частые проблемы

### ImagePullBackOff или долгий ContainerCreating

На свежем Docker Desktop это чаще всего связано с долгой загрузкой образов или временным сетевым сбоем registry.

Что проверить:

```bash
kubectl describe pod -n <namespace> <pod>
```

Если ошибка похожа на `unexpected EOF`, обычно помогает повторный pull или перезапуск pod'а.

### AWX долго стартует

AWX поднимает PostgreSQL, web, task, миграции и execution environment. Первый запуск может занять несколько минут.

Что смотреть:

```bash
kubectl get pods -n awx
kubectl logs -n awx job/awx-demo-migration-24.6.1 --tail=100
```

### Argo CD Application не Synced

Проверить:

```bash
kubectl describe application -n argocd ansible-os-pods
```

Типовые причины:

- Gitea repo еще не создан или не запушен;
- указан неверный path;
- repo-server Argo CD еще не готов.

### AWX job successful, но hosts skipped

Значит playbook не нашел группу inventory. В этом проекте playbook ожидает группу `linux_pods`.

Проверить в AWX:

- inventory `Demo OS pods`;
- group `linux_pods`;
- hosts `ol-node-1.demo-os.svc.cluster.local` и `ol-node-2.demo-os.svc.cluster.local`.

## Очистка

```bash
./scripts/destroy.sh
```

Скрипт удаляет namespaces:

- `demo-os`
- `awx`
- `gitea`
- `argocd`


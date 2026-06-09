# Practicum: сквозной GitOps + DVP сценарий

## Цель

Показать три актуальных сценария нового стенда: выпуск golden image, заказ
окружения через Git или Web и автоматическое удаление после TTL.

## Исходное состояние

- context: `practicum-tks-api.d8case.ru`;
- namespace: `practicum-tks`;
- Argo CD Application `practicum-demo` — `Synced/Healthy`;
- active image: `practicum-alpine-golden-3-23-v2`;
- portal: `https://selfservice-practicum.d8case.ru`.

## Golden image

1. В Gitea откройте `gitops/environments/practicum/golden-images/`.
2. Покажите URL source image, минимальный builder и versioned `VirtualImage`.
3. В AWX откройте workflow `Practicum Golden Image Build`.
4. Покажите успешный workflow job `40`: prepare, validate, shutdown.
5. В Argo CD покажите v1 и v2. Подчеркните, что v1 не изменялся.
6. В `catalog.yaml` покажите отдельное переключение `activeGoldenImage`.

Проверка:

```bash
kubectl get vi,vd,vm -n practicum-tks -o wide
kubectl get cm practicum-golden-image-catalog -n practicum-tks -o yaml
```

## Git self-service

Создайте JSON-formatted YAML в
`gitops/self-service/practicum/requests/<environment>.yaml`:

```json
{
  "apiVersion": "demo.practicum/v1",
  "kind": "EnvironmentRequest",
  "metadata": {"name": "practicum-env-marina-demo-001"},
  "spec": {
    "owner": "marina-volkova-practicum",
    "email": "marina.volkova.practicum@demo.local",
    "groups": ["practicum-qa-devs"],
    "profile": "app-with-vm",
    "purpose": "demo",
    "ttl": "2h",
    "createdAt": "2026-06-09T12:00:00Z"
  }
}
```

После push controller создаёт generated-каталог, Argo CD применяет app/VM, AWX
запускает post-config. Все ресурсы остаются в `practicum-tks`.

## Web self-service

1. Откройте `https://selfservice-practicum.d8case.ru`.
2. Войдите пользователем Alice, Boris или Marina.
3. Выберите разрешённый профиль, purpose и TTL.
4. Нажмите `Отправить заявку`.
5. Покажите environment ID отдельно от namespace.
6. Дождитесь `Ready` и успешного AWX job.

Проверенный результат: `practicum-env-alice-feature-019354`, приложение `1/1`,
VM `Running`, IP `10.66.0.46`, `AgentReady=True`, AWX job `55` successful.

## TTL cleanup

Controller переводит request в `Expired`, удаляет environment из generated
kustomization, архивирует request и записывает `Cleaned`. Argo CD prune удаляет
только объекты с label данного environment.

```bash
kubectl get all,vd,vm -n practicum-tks \
  -l demo.practicum/environment=<environment-id>
```

Namespace, Argo CD, AWX, Gitea, portal и другие окружения сохраняются.

## Пояснение для демонстратора

Разработчик не получает право создавать VM или менять Kubernetes напрямую. Он
формулирует намерение через утверждённый request. Git хранит намерение и
результат генерации, Argo CD приводит кластер к desired state, DVP создаёт VM, а
AWX отвечает за процедурную настройку гостевой ОС. TTL реализован тем же путём:
сначала меняется Git, затем Argo CD безопасно удаляет только принадлежащие
заявке ресурсы.

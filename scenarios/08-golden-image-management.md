# 08. Golden Image Management

## Цель

Показать production-like сценарий управления golden image: администратор задаёт в Git ссылку на исходный cloud image, DVP импортирует его в кластер, затем builder VM подготавливается через AWX и из неё публикуется новая версия golden image.

## Исходное состояние

- Argo CD Application `demo-platform` синхронизирует `gitops/environments/prod`.
- DVP CRD доступны в кластере.
- AWX Project `Gitea demo repo` смотрит на тот же Git-репозиторий.
- Для стенда используются минимальные ресурсы: `1` core, `coreFraction: 5%`, `512Mi` RAM, disk `256Mi`.

## Что меняем в Git

Администратор указывает источник базового образа в Git:

```text
gitops/environments/prod/golden-images/source-image.yaml
```

Ключевая часть:

```yaml
spec:
  storage: ContainerRegistry
  dataSource:
    type: HTTP
    http:
      url: https://dl-cdn.alpinelinux.org/alpine/v3.23/releases/cloud/generic_alpine-3.23.3-x86_64-bios-cloudinit-r0.qcow2
```

Параметры также отражены в:

```text
gitops/environments/prod/values.yaml
```

В текущем plain-YAML демо `values.yaml` является человекочитаемым паспортом параметров, а реальный DVP import выполняется из `source-image.yaml`.

## Пошаговое выполнение

### 1. Показать source image в Git

Откройте Gitea:

```text
http://gitea-awx.d8.kir.lab
```

Файл:

```text
gitops/environments/prod/golden-images/source-image.yaml
```

Что сказать:

> Администратор не скачивает image руками и не загружает его через UI. Он указывает URL исходного cloud image в Git. Argo CD применяет `VirtualImage`, а DVP импортирует образ в кластер.

### 2. Применить импорт через GitOps

Если файл уже в Git, достаточно дождаться Argo CD. Для ручного ускорения:

```bash
kubectl annotate application -n argocd demo-platform argocd.argoproj.io/refresh=hard --overwrite
```

Проверка:

```bash
kubectl get vi alpine-base-3-23-v1 -n demo-prod -o wide
```

Ожидаемо:

```text
PHASE Ready
PROGRESS 100%
```

### 3. Проверить builder disk и builder VM

```bash
kubectl get vd golden-builder-root -n demo-prod -o wide
kubectl get vm golden-builder-vm -n demo-prod -o wide
```

Ожидаемо:

- `golden-builder-root` создан из `alpine-base-3-23-v1`;
- `golden-builder-vm` существует, но имеет `runPolicy: Manual`, чтобы не расходовать ресурсы без необходимости.

### 4. Запустить builder VM для customization

Для живого прогона можно временно изменить в Git:

```text
gitops/environments/prod/golden-images/builder-vm.yaml
```

Было:

```yaml
runPolicy: Manual
```

Стало:

```yaml
runPolicy: AlwaysOnUnlessStoppedManually
```

Затем:

```bash
git add gitops/environments/prod/golden-images/builder-vm.yaml
git commit -m "Start golden image builder VM"
git push origin main
git push dkp-gitea main
```

Проверка:

```bash
kubectl get vm golden-builder-vm -n demo-prod -o wide
```

### 5. Запустить AWX customization

В AWX создайте inventory host `golden-builder-vm` в группе:

```text
golden_builder
```

Variables:

```yaml
ansible_host: <IP golden-builder-vm>
```

Запустите playbook:

```text
gitops/awx/playbooks/prepare-golden-image.yml
```

Он:

- устанавливает пакеты;
- включает `qemu-guest-agent`;
- пишет demo config;
- чистит кеши и логи;
- очищает machine-id там, где это применимо;
- удаляет SSH host keys для регенерации на первом boot.

### 6. Выполнить validation

Запустите:

```text
gitops/awx/playbooks/validate-golden-image.yml
```

Проверяется:

- SSH/Python доступ;
- наличие `qemu-ga`;
- наличие `/etc/golden-image-demo.conf`.

### 7. Опубликовать новую версию golden image

После успешной подготовки и проверки примените manifest:

```text
gitops/environments/prod/golden-images/publish-golden-image.example.yaml
```

В production лучше делать это отдельным Git commit после validation:

```bash
cp gitops/environments/prod/golden-images/publish-golden-image.example.yaml \
   gitops/environments/prod/golden-images/alpine-golden-3-23-v1.yaml
```

Добавьте новый файл в `golden-images/kustomization.yaml`, сделайте commit и push.

Проверка:

```bash
kubectl get vi alpine-golden-3-23-v1 -n demo-prod -o wide
```

### 8. Переключить потребителей

Дальше рабочие VM или VM templates переводятся с base image на новую версию golden image через Git:

```yaml
objectRef:
  kind: VirtualImage
  name: alpine-golden-3-23-v1
```

## Что показывать в Argo CD

- `VirtualImage/alpine-base-3-23-v1` импортируется из URL.
- `VirtualDisk/golden-builder-root` создаётся из импортированного image.
- `VirtualMachine/golden-builder-vm` управляется GitOps.
- Новая версия golden image появляется как отдельный artifact после validation.

## Что показывать в AWX

- Job `prepare-golden-image.yml`.
- Job `validate-golden-image.yml`.
- Stdout с установкой пакетов, включением `qemu-guest-agent` и validation summary.

## Проверка через kubectl

```bash
kubectl get vi -n demo-prod -o wide
kubectl get vd golden-builder-root -n demo-prod -o wide
kubectl get vm golden-builder-vm -n demo-prod -o wide
kubectl describe vi alpine-base-3-23-v1 -n demo-prod
```

## Ожидаемый результат

- DVP импортировал исходный image из URL, заданного в Git.
- Builder disk создан из imported image.
- Builder VM готова к customization через AWX.
- После validation можно опубликовать новую immutable-версию golden image.

## Rollback

Rollback выполняется через Git:

```bash
git revert HEAD
git push origin main
git push dkp-gitea main
```

Для production-модели не перезаписывайте существующий golden image. Создавайте новую версию:

```text
alpine-golden-3-23-v1
alpine-golden-3-23-v2
```

Тогда rollback означает переключение потребителей обратно на предыдущую версию.

## Пояснение для демонстратора

На этом сценарии важно подчеркнуть, что golden image — это не ручной артефакт, загруженный через UI. Источник образа, builder VM, playbooks настройки и публикация версии описаны в Git. Argo CD отвечает за DVP-ресурсы, AWX — за изменение ОС внутри builder VM, а Git сохраняет историю: из какого URL был импортирован образ, каким playbook'ом он был подготовлен и на какую версию переключили потребителей.

## План рассказа для живого демо

### 0. Вводная

Что сказать:

> В production одна из частых задач платформенной команды — управление golden image. Нужно регулярно брать новый исходный cloud image, добавлять в него корпоративные пакеты, агенты, конфиги, security baseline и публиковать новую версию для команд.

Ключевая мысль:

> Мы хотим, чтобы выбор исходного image, процесс подготовки и переключение потребителей были управляемыми через Git, а не через ручную загрузку в UI.

### 1. Показать Git как точку выбора исходного образа

Открыть Gitea:

```text
http://gitea-awx.d8.kir.lab
```

Открыть файл:

```text
gitops/environments/prod/golden-images/source-image.yaml
```

Показать поле:

```yaml
spec:
  dataSource:
    type: HTTP
    http:
      url: ...
```

Что сказать:

> Вот ответ на вопрос “откуда берём новый изначальный образ”. Администратор меняет эту ссылку в Git. Например, сегодня это Alpine cloud image, завтра это новый Ubuntu cloud image или корпоративный base image, опубликованный в approved repository.

Ожидаемый вопрос аудитории:

> А если URL поменяли?

Ответ:

> Лучше не перезаписывать старый image с тем же именем, а создать новую версию: `ubuntu-base-v1`, `ubuntu-base-v2`. Тогда rollback — это обычный Git revert или переключение потребителей на предыдущую версию.

### 2. Показать Argo CD как механизм импорта в DVP

Открыть Argo CD:

```text
http://argocd-awx.d8.kir.lab
```

Открыть Application:

```text
demo-platform
```

Показать resource tree:

```text
VirtualImage/alpine-base-3-23-v1
VirtualDisk/golden-builder-root
VirtualMachine/golden-builder-vm
```

Команды:

```bash
kubectl get vi alpine-base-3-23-v1 -n demo-prod -o wide
kubectl get vd golden-builder-root -n demo-prod -o wide
kubectl get vm golden-builder-vm -n demo-prod -o wide
```

Что сказать:

> Argo CD не скачивает image сам. Он применяет DVP `VirtualImage`. После этого DVP-контроллер импортирует образ из URL и кладёт его во внутреннее хранилище.

### 3. Объяснить builder VM

Открыть файл:

```text
gitops/environments/prod/golden-images/builder-vm.yaml
```

Показать:

```yaml
runPolicy: Manual
cpu:
  cores: 1
  coreFraction: 5%
memory:
  size: 512Mi
```

Что сказать:

> Builder VM — временная машина для подготовки образа. Она минимальная и по умолчанию в `Manual`, чтобы не расходовать ресурсы стенда. Когда нужно подготовить новую версию, мы включаем её через Git, запускаем AWX customization и после проверки публикуем image.

### 4. Показать AWX как слой customization

Открыть AWX:

```text
http://awx-demo.d8.kir.lab
```

Открыть Project:

```text
Gitea demo repo
```

Показать playbooks:

```text
gitops/awx/playbooks/prepare-golden-image.yml
gitops/awx/playbooks/validate-golden-image.yml
```

Что сказать:

> Argo CD создал builder VM, но не должен заниматься настройкой ОС. AWX выполняет то, что обычно входит в golden image baseline: пакеты, агенты, конфиги, очистка логов, подготовка к клонированию и validation.

### 5. Показать, что именно меняет AWX

Открыть в Gitea:

```text
gitops/awx/playbooks/prepare-golden-image.yml
```

Показать задачи:

- установка `qemu-guest-agent`, `chrony`, `curl`, `jq`;
- включение `qemu-guest-agent`;
- запись `/etc/golden-image-demo.conf`;
- очистка cache/logs;
- очистка machine-id и SSH host keys.

Что сказать:

> Это процедурная часть. Она версионируется в Git, но выполняется AWX внутри ОС builder VM.

### 6. Показать validation

Открыть:

```text
gitops/awx/playbooks/validate-golden-image.yml
```

Что сказать:

> Перед публикацией golden image мы проверяем, что VM доступна, qemu guest agent установлен, а demo config применён. В production сюда добавляются security checks, compliance checks, версии агентов и smoke tests.

### 7. Публикация golden image

Открыть:

```text
gitops/environments/prod/golden-images/publish-golden-image.example.yaml
```

Что сказать:

> Этот файл намеренно example. Мы не публикуем golden image автоматически до customization и validation. После успешной проверки создаётся отдельный Git commit, который добавляет новую версию image, например `alpine-golden-3-23-v1`.

Ключевая мысль:

> Golden image должен быть immutable. Новая версия — новый объект. Не перетираем старый image.

### 8. Переключение потребителей

Показать идею:

```yaml
objectRef:
  kind: VirtualImage
  name: alpine-golden-3-23-v1
```

Что сказать:

> Рабочие VM или шаблоны VM переключаются на новую версию через Git. Если новая версия плохая, rollback — это Git revert на предыдущий image reference.

### 9. Финальная формулировка

> В этом сценарии Git отвечает за выбор исходного image и версию golden image, Argo CD — за DVP-ресурсы и импорт, AWX — за настройку ОС внутри builder VM, а DVP — за хранение и запуск VM-образов. Это воспроизводимый pipeline управления golden image без ручной загрузки и без неявных изменений.

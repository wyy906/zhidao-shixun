#!/usr/bin/env bash
# 生产节点预检（只读，不修改系统，不输出任何密钥）
# 退出码：0=全部通过；1=存在 FAIL；2=无 FAIL 但存在 BLOCK
set -u

ENV_FILE=${ZD_ENV_FILE:-/etc/zd-sandbox/manager.env}
PASS=0
FAIL=0
BLOCK=0

ok() { echo "PASS   $*"; PASS=$((PASS + 1)); }
bad() { echo "FAIL   $*"; FAIL=$((FAIL + 1)); }
block() { echo "BLOCK  $*"; BLOCK=$((BLOCK + 1)); }
info() { echo "INFO   $*"; }

if [ "$(id -u)" -ne 0 ]; then
  echo "BLOCK  请用 root 运行预检（需要读取 manager.env 与证书）"
  exit 2
fi

echo "== 系统 =="
if command -v lsb_release >/dev/null 2>&1; then
  info "$(lsb_release -ds 2>/dev/null)"
fi
info "kernel=$(uname -r) arch=$(uname -m)"
if [ "$(uname -m)" = "x86_64" ]; then ok "架构 x86_64"; else bad "生产节点要求 x86_64"; fi

if [ "$(stat -fc %T /sys/fs/cgroup 2>/dev/null)" = "cgroup2fs" ]; then
  ok "cgroup v2"
else
  bad "cgroup v2 未启用（CPU/内存/PID 限额依赖 cgroup v2）"
fi

echo "== Docker =="
if docker version --format '{{.Server.Version}}' >/tmp/zd_preflight_docker 2>/dev/null; then
  ok "Docker Engine $(cat /tmp/zd_preflight_docker)"
  driver=$(docker info --format '{{.CgroupDriver}}' 2>/dev/null)
  if [ "$driver" = "systemd" ]; then ok "Docker cgroup driver=systemd"; else info "Docker cgroup driver=$driver"; fi
else
  bad "Docker 不可用"
fi
if [ -S /var/run/docker.sock ]; then
  ok "Docker socket 存在"
  info "docker.sock 权限=$(stat -c '%a %U:%G' /var/run/docker.sock)"
else
  bad "Docker socket 不存在"
fi

echo "== 内核隔离 =="
if [ "$(cat /sys/module/apparmor/parameters/enabled 2>/dev/null)" = "Y" ]; then
  ok "AppArmor 已启用"
else
  bad "AppArmor 未启用（生产建议启用并配置 profile）"
fi

if [ -f "$ENV_FILE" ]; then
  # shellcheck disable=SC1090
  set -a
  . "$ENV_FILE"
  set +a
  ok "已加载 $ENV_FILE"
else
  bad "找不到 $ENV_FILE"
fi

if [ -n "${ZD_SANDBOX_RUNTIME:-}" ]; then
  if docker info --format '{{json .Runtimes}}' 2>/dev/null | grep -q "\"${ZD_SANDBOX_RUNTIME}\""; then
    ok "运行时 ${ZD_SANDBOX_RUNTIME} 已注册"
  else
    bad "运行时 ${ZD_SANDBOX_RUNTIME} 未注册"
  fi
else
  info "未配置 gVisor/runsc（可选增强项）"
fi

echo "== 配置与证书 =="
perm=$(stat -c '%a' "$ENV_FILE" 2>/dev/null)
owner=$(stat -c '%U:%G' "$ENV_FILE" 2>/dev/null)
case "$perm" in
  600|640) ok "manager.env 权限 $perm（$owner）" ;;
  *) bad "manager.env 权限 $perm，应为 600 或 640" ;;
esac

token=$(grep -E '^[[:space:]]*ZD_SANDBOX_TOKEN=' "$ENV_FILE" 2>/dev/null | tail -1 | cut -d= -f2-)
if [ "${#token}" -ge 32 ]; then
  ok "管理令牌长度 >= 32"
else
  bad "管理令牌缺失或长度不足 32"
fi
unset token

image=${ZD_SANDBOX_IMAGE:-}
if printf '%s' "$image" | grep -Eq '@sha256:[0-9a-f]{64}$|^sha256:[0-9a-f]{64}$'; then
  ok "镜像引用已固定 digest"
else
  bad "镜像引用未固定 digest：$image"
fi
if [ -n "$image" ] && docker image inspect "$image" >/dev/null 2>&1; then
  ok "本地镜像存在"
  if printf '%s' "$image" | grep -q '@sha256:'; then
    digest=${image#*@}
    if docker inspect --format '{{json .RepoDigests}}' "$image" 2>/dev/null | grep -q "$digest"; then
      ok "RepoDigests 包含固定 digest"
    else
      bad "本地 RepoDigests 不包含 $digest（可能未按该 digest 拉取）"
    fi
  fi
else
  bad "本地镜像不存在：$image"
fi

if [ "${ZD_SANDBOX_ALLOW_INSECURE_HTTP:-false}" = "true" ]; then
  block "明文 HTTP 已开启：仅允许回环开发，生产必须关闭"
else
  for f in "${ZD_SANDBOX_TLS_CERT:-}" "${ZD_SANDBOX_TLS_KEY:-}"; do
    if [ -n "$f" ] && [ -r "$f" ]; then
      ok "证书文件可读：$f"
    else
      bad "证书文件缺失或不可读：$f"
    fi
  done
  key=${ZD_SANDBOX_TLS_KEY:-}
  if [ -n "$key" ] && [ -r "$key" ]; then
    kp=$(stat -c '%a' "$key")
    case "$kp" in
      600|640) ok "私钥权限 $kp" ;;
      *) bad "私钥权限 $kp，应为 600/640" ;;
    esac
  fi
  if [ -n "${ZD_SANDBOX_TLS_CLIENT_CA:-}" ]; then
    if [ -r "$ZD_SANDBOX_TLS_CLIENT_CA" ]; then ok "双向 TLS 客户端 CA 可读"; else bad "双向 TLS 客户端 CA 不可读"; fi
  else
    info "未启用双向 TLS（生产建议启用）"
  fi
fi

if [ -n "${ZD_SANDBOX_INSTANCE_ID:-}" ]; then
  ok "实例标识已显式设置"
else
  block "未设置 ZD_SANDBOX_INSTANCE_ID（默认主机名，多实例必须显式设置）"
fi

echo "== systemd 与运行状态 =="
if systemctl is-active --quiet zd-sandbox 2>/dev/null; then
  ok "zd-sandbox 服务运行中"
else
  bad "zd-sandbox 服务未运行"
fi
svc_user=$(systemctl show -p User --value zd-sandbox 2>/dev/null)
if [ "$svc_user" = "zd-sandbox" ]; then
  ok "服务使用专用非 root 账号"
else
  bad "服务账号为 '$svc_user'，应为 zd-sandbox"
fi
if systemctl show -p NoNewPrivileges --value zd-sandbox 2>/dev/null | grep -qi yes; then
  ok "systemd NoNewPrivileges=yes"
else
  bad "systemd 未启用 NoNewPrivileges"
fi

echo "== 容量与残留 =="
free_gb=$(df -P /var/lib/docker 2>/dev/null | awk 'NR==2 {print int($4/1024/1024)}')
if [ -n "$free_gb" ] && [ "$free_gb" -ge 10 ]; then
  ok "Docker 数据目录剩余 ${free_gb}GB"
else
  bad "Docker 数据目录剩余空间不足 10GB（${free_gb:-unknown}GB）"
fi
residual=$(docker ps -aq --filter label=zd.sandbox=1 2>/dev/null | wc -l)
if [ "$residual" -eq 0 ]; then
  ok "无 zd.sandbox 残留容器"
else
  bad "存在 $residual 个 zd.sandbox 残留容器"
fi

echo
echo "结果：PASS=$PASS FAIL=$FAIL BLOCK=$BLOCK"
if [ "$FAIL" -gt 0 ]; then exit 1; fi
if [ "$BLOCK" -gt 0 ]; then exit 2; fi
exit 0

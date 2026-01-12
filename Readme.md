📊 Auditoria Automática de Recursos em Linux


Sistemas Linux em uso contínuo tendem a apresentar degradação gradual de desempenho causada por:

Pressão de memória RAM e swap

Crescimento descontrolado de logs

Saturação silenciosa de partições (/, /var, /home)

Falta de histórico para análise de tendência

Esses fatores raramente causam falha imediata, mas levam a quase travamentos, latência elevada e comportamento instável.

O objetivo deste projeto foi detectar sinais precoces de exaustão de recursos, registrar histórico diário e gerar recomendações técnicas objetivas.

**Objetivo

Criar uma ferramenta de auditoria automática que:

Monitore RAM, swap e disco

Identifique riscos antes do travamento

Gere análise e recomendações técnicas

Armazene histórico para análise de tendência

Funcione sem dependências externas ou agentes pesados

Arquitetura da Solução

![Relátorio no terminal](https://github.com/lcnjrj/linux_resource_audit/tree/main/imagens)

O projeto foi implementado como um pipeline ETL em Python:

🔹 Extract

psutil para RAM, swap e disco

journalctl para sinais de OOM e falta de espaço

Coleta focada em /, /var e /home

🔹 Transform

Classificação automática de risco:

RAM_CRITICAL

SWAP_CRITICAL

DISK_CRITICAL

Cálculo de:

RAM ideal recomendada

Tamanho de disco ideal por partição

Geração de análise textual técnica

Normalização para persistência histórica

🔹 Load

JSON → relatório detalhado

CSV → métricas simples

SQLite → histórico diário para tendência

Output colorido no terminal (estilo btop++)

Execução
python3 linux_resource_audit.py

Exemplo de saída no terminal
Linux Resource Audit  2026-01-09T10:22:14

Risco:
● SWAP_CRITICAL
● DISK_CRITICAL:/
● DISK_CRITICAL:/var
● DISK_CRITICAL:/home

Memória:
RAM: 5.8 / 8.0 GB (72%)
Swap: 68% CRÍTICO
→ RAM recomendada: 12 GB

Disco:
/      42 / 50 GB (84%) → recomendado: 59 GB
/var   18 / 20 GB (90%) → recomendado: 26 GB
/home  72 / 80 GB (90%) → recomendado: 101 GB

Histórico e Tendência

Cada execução grava um snapshot diário no SQLite:

audit_history.db

Consulta de tendência de memória
SELECT
  date(timestamp) AS dia,
  ROUND(AVG(ram_used_pct), 2) AS ram_media
FROM audits
GROUP BY dia
ORDER BY dia;

Exemplo de resultado
2026-01-05 | 42.18
2026-01-06 | 47.03
2026-01-07 | 55.61
2026-01-08 | 61.92


➡️ Permite identificar crescimento progressivo, vazamentos de memória ou necessidade de tuning.

Recomendações Automáticas Geradas
🔹 Memória

Cálculo baseado em uso real + margem de segurança

Identifica pressão de swap como indicador crítico

🔹 Disco

Recomenda tamanho ideal por partição

Prioriza /var e /home como pontos de risco comuns

🔹 Logs (journald)

Sugestão automática de limites:

SystemMaxUse=500M
SystemKeepFree=1G
RuntimeMaxUse=200M
MaxFileSec=7day

Automação

Execução diária via cron:

0 2 * * * /usr/bin/python3 /path/linux_resource_audit.py


Histórico contínuo

Baixo impacto

Zero dependência de serviços externos

**Benefícios

Detecção precoce de quase travamentos

Base objetiva para upgrade de hardware

Evidência técnica para decisões de capacidade

Ferramenta leve, auditável e transparente

Ideal para servidores, desktops Linux e laboratórios

**Tecnologias Utilizadas

Python 3

psutil

SQLite

journalctl

ANSI terminal colors

Linux userland

**Possíveis Evoluções

Detecção automática de tendência crítica

Alertas por e-mail ou webhook

Gráficos ASCII ou exportação para Grafana

Análise por processo

# Product Vision — Seller Intelligence

## 1. Visão

> Ser a camada de inteligência que todo vendedor de marketplace usa para transformar dados
> operacionais fragmentados (produtos, pedidos, estoque, custos, anúncios) em decisões de
> negócio rápidas e confiáveis — começando pelos vendedores Shopee que operam com o Bling ERP.

## 2. O Problema

Vendedores de marketplace no Brasil operam hoje com dados espalhados em múltiplos sistemas
que não conversam entre si:

- O **marketplace** (Shopee) mostra vendas e anúncios, mas não custos reais nem lucro líquido.
- O **ERP** (Bling) centraliza produtos, pedidos e estoque, mas não foi desenhado para
  inteligência de negócio nem para decisões de precificação/ads.
- **Planilhas paralelas** viram a única forma de juntar custo de produto, taxas do marketplace,
  frete, comissão de afiliado e ROI de campanha — processo manual, sujeito a erro, sem histórico
  e impossível de escalar conforme o catálogo cresce.

Resultado: o vendedor toma decisões de precificação, estoque e investimento em ads no escuro,
sem saber com precisão qual produto realmente dá lucro.

## 3. Público-Alvo

**Segmento inicial (MVP):** sellers de Shopee que já usam o Bling como ERP, faturando o
suficiente para sentir dor de gestão manual (tipicamente centenas a milhares de pedidos/mês,
catálogo de dezenas a milhares de SKUs).

**Personas primárias:**
- **Dono/Gestor da operação** — decide precificação, sortimento e investimento em ads.
- **Analista/Operacional** — acompanha estoque, pedidos e reposição no dia a dia.

**Expansão futura:** sellers multi-marketplace (Mercado Livre, Amazon, Magalu, TikTok Shop) e
multi-ERP (Tiny, Omie, ERPs próprios), agências que gerenciam múltiplos sellers.

## 4. Proposta de Valor

| Dor | Solução Seller Intelligence |
|---|---|
| Dados espalhados entre Shopee, Bling e planilhas | Central única que integra e consolida tudo |
| Não sabe o lucro real por SKU | Custo, taxas e margem calculados automaticamente por pedido/produto |
| Não sabe se a operação está saudável | **Seller Score**: nota consolidada de saúde do negócio |
| Decisões demoram por falta de visão consolidada | Dashboards e KPIs em tempo (quase) real |
| Análise de dados exige expertise técnica | **Copilot com IA** responde perguntas de negócio em linguagem natural |

## 5. Diferenciais

1. **Foco vertical** — feito para a realidade de marketplace + ERP brasileiro, não um BI genérico.
2. **Seller Score** — métrica proprietária que resume saúde financeira e operacional em um número
   acionável, com plano de melhoria.
3. **Copilot com IA** — interface conversacional sobre os dados do próprio seller ("qual produto
   perdeu margem esse mês e por quê?").
4. **Arquitetura multi-marketplace/multi-ERP desde o dia 1** — o MVP nasce estreito (Shopee +
   Bling) mas o core de domínio já é desenhado para plugar novas fontes sem retrabalho.
5. **Multi-tenant nativo** — pronto para vender como SaaS desde o primeiro cliente, sem
   migração posterior de arquitetura single-tenant.

## 6. Métricas de Sucesso (North Star e apoio)

- **North Star:** nº de tenants ativos que consultam o dashboard/Copilot ≥ 3x por semana.
- Tempo médio para primeira sincronização completa (Shopee + Bling) < 15 minutos.
- % de pedidos com custo e margem calculados corretamente (sem intervenção manual).
- Adoção do Copilot: % de tenants que fazem ao menos 1 pergunta/semana.
- Retenção mensal de tenants pagantes (churn < X%, a definir com dados de mercado).

## 7. Fora de Escopo (por ora)

- Marketplaces além de Shopee e ERPs além de Bling no MVP (arquitetura permite, mas não é
  entregue inicialmente).
- Emissão fiscal, conciliação bancária completa ou funcionalidades de ERP financeiro completo
  (o produto consome dados financeiros, não substitui o ERP/contabilidade).
- App mobile nativo (web responsivo cobre o MVP).

## 8. Visão de Longo Prazo

Seller Intelligence se torna o "cockpit" padrão de qualquer operação de marketplace no Brasil,
com cobertura multi-marketplace e multi-ERP, IA que não só responde perguntas mas recomenda e,
com aprovação do seller, executa ações (reprecificação, pausar campanha, sugerir reposição de
estoque).

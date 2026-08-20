# 性能与配置

## 推荐配置基线（application.yml）

```yaml
spring:
  jpa:
    open-in-view: false                 # 见 transactions-and-locking.md，一律显式关闭
    hibernate:
      ddl-auto: validate                # 生产只校验不建表，DDL 归迁移工具管
    properties:
      hibernate:
        default_batch_fetch_size: 100   # N+1 全局安全网：懒加载合并成 in (...)
        jdbc:
          batch_size: 50                # 批量写（IDENTITY 主键的 insert 享受不到）
        order_inserts: true             # 按表分组重排,让 batch 真正凑满
        order_updates: true
  datasource:
    hikari:
      maximum-pool-size: 20             # 按 DB 核数与实例数算,不是越大越好
      minimum-idle: 5
      connection-timeout: 30000
      max-lifetime: 1800000             # 略小于 DB/中间件的空闲断连时间
```

开发环境追加 SQL 观测（**生产别开**）：

```yaml
logging:
  level:
    org.hibernate.SQL: DEBUG                 # 打印 SQL
    org.hibernate.orm.jdbc.bind: TRACE       # 打印绑定参数（Hibernate 6+ 的 logger 名）
spring:
  jpa:
    properties:
      hibernate:
        format_sql: true
```

`spring.jpa.show-sql=true` 是往 stdout 裸打，不走日志框架，别用。

## SQL 条数是第一性能指标

写完一个接口，看一眼日志里它发了几条 SQL——这比任何猜测都可靠：

- 列表接口出现 1+N 条同形状 SQL → N+1，按 relationships.md 治理。
- 加保险丝让问题在测试期炸出来而不是上线后：

```properties
spring.jpa.properties.hibernate.query.fail_on_pagination_over_collection_fetch=true
```

- 定量分析用 `hibernate.generate_statistics=true` + `logging.level.org.hibernate.stat=DEBUG`，
  每个 Session 输出查询数、缓存命中、flush 耗时；更细的用 datasource-proxy 或 p6spy 包一层。
- 测试里断言 SQL 条数的做法见 `spring-jpa-testing` skill。

## 批量写入

`saveAll` 逐条 `EntityManager.persist`，光有它不算批量——要凑齐三件套：

1. `hibernate.jdbc.batch_size=50` + `order_inserts/order_updates=true`（见上面基线）
2. **主键不能是 `IDENTITY`**（insert 必须逐条执行拿自增值，batch 直接失效）；
   PostgreSQL 用 SEQUENCE + `allocationSize=50`，MySQL 大批量导入考虑绕开 JPA 用 JdbcTemplate batch
3. MySQL JDBC URL 加 `rewriteBatchedStatements=true`，驱动把 batch 重写成多值 insert

大批量循环里防一级缓存膨胀：每 batch_size 条 `em.flush(); em.clear();`。
十万行以上的导入导出别走 JPA，用 `JdbcTemplate`/`JdbcClient` 或数据库原生 COPY/LOAD。

## 一级 / 二级缓存

- 一级缓存跟着 `EntityManager`（即事务）走：同事务内 `findById` 同 id 不会二次查库；
  这也是 `@Modifying` 之后必须 clear 的原因（缓存里是旧值）。
- 二级缓存（跨 Session）**默认别开**。它只拦 `findById` 类加载，查询走 query cache 另算，
  失效策略和集群一致性都是坑。读多写少的热点数据，优先在 Service 层用 Spring Cache
  （`@Cacheable` + Redis/Caffeine）缓存 **DTO**——边界清楚、失效可控、缓存的不是托管实体。

## 连接池（HikariCP）

- `maximum-pool-size` 经验公式：`(CPU 核数 * 2) + 磁盘数`，指**数据库侧**的核数；
  多实例部署记得乘实例数不能超过 DB 的 `max_connections`。池子过大只会让 DB 上下文切换更糟。
- 事务里干慢活（外部调用）是连接耗尽的头号原因，先治事务再调池子。
- 排查泄漏：`spring.datasource.hikari.leak-detection-threshold=60000`，
  连接借出超 60s 打堆栈。

## Schema 管理

- **生产 DDL 只能来自 Flyway/Liquibase 迁移脚本**，`ddl-auto` 生产永远 `validate`
  （`update` 不会删列改类型，漂移无声积累；`create*` 是灾难）。
- 实体上的 `@Index`/`@UniqueConstraint` 声明要和迁移脚本一致——前者是文档和测试库建表用，
  后者才是生产真相。
- 迁移脚本只追加、不回改已发布的版本；破坏性变更（删列改列）走 expand → migrate → contract
  三步，和代码发布解耦。

## 大字段与慢查询

- `@Lob`/大 JSON 列放进常用实体会拖慢所有查询——列表查询用投影绕开大列，
  或把大字段拆到附表按需加载。
- 慢查询治理顺序：先 `explain` 看执行计划 → 补/改索引 → 改写查询（避免函数包索引列）
  → 最后才考虑缓存。JPA 生成的 SQL 通过上面的日志拿到原文再分析。

## 需要绕开 JPA 的信号

出现以下情况说明该换工具，不要硬撑：

- 报表/聚合大 SQL（CTE、窗口函数）→ `JdbcClient` / JOOQ / 自定义 fragment 写原生 SQL
- 十万行级批量导入导出 → JDBC batch / 数据库原生工具
- 全文检索 → 数据库全文索引或搜索引擎，别用 `like '%x%'`

JPA 的甜区是「实体为中心的 OLTP 读写」，超出甜区的部分混合架构是常态。

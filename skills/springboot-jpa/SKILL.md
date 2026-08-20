---
name: springboot-jpa
description: Spring Boot / Spring Data JPA 生产代码的模式与决策:实体设计、关联关系、Repository 查询、事务与锁、N+1 治理、性能配置。凡是要写或改 @Entity、JpaRepository、@Query、@Transactional,设计表映射与关联(@OneToMany/@ManyToOne/@ManyToMany),做分页/投影/动态查询(Specification),处理 LazyInitializationException、N+1、乐观锁悲观锁、批量读写、HikariCP/Flyway 配置时,先读本 skill 再动手。触发词:JPA、Hibernate、实体、Entity、JpaRepository、@Query、@Modifying、懒加载、N+1、join fetch、@EntityGraph、投影、Projection、DTO 查询、分页、Pageable、keyset、Specification、@Transactional、乐观锁、@Version、悲观锁、软删除、审计、@EnableJpaAuditing、open-in-view、ddl-auto、HikariCP。不适用于:JPA 测试(用 spring-jpa-testing)、MyBatis/JOOQ/R2DBC/MongoDB、通用 Spring Boot 工程惯例(用 java-springboot)。
---

# Spring Boot JPA 模式

写生产级 JPA 代码的决策手册。核心立场:**实体图是给写路径用的,读路径用投影;
懒加载是默认,取数据靠显式 fetch;事务短、边界在 Service;SQL 条数是第一性能指标。**

分工:本 skill 管生产代码;JPA 测试(@DataJpaTest/TestEntityManager/Testcontainers)
用 `spring-jpa-testing`;通用 Spring Boot 惯例(分层、DTO、异常处理)用 `java-springboot`。

## 第 0 步:先看项目已有约定

动手前扫 2~3 个现有实体和 repository(`grep -rl "@Entity" src/main/java | head -3`),确认:

- ID 策略(IDENTITY / SEQUENCE / UUID)、Lombok 用法、命名显式还是隐式、包结构、
  审计基类有没有
- **有约定跟约定,新旧不一致比次优约定伤害大**;没有约定才用下面的默认值
- 顺手确认版本:Boot 3.x → Spring Data JPA 3.x / Hibernate 6,Boot 4 → 4.x / Hibernate 7
  (references 里标了「3.1+」「4.0+」的 API 用前先对版本)

## 默认决策表

| 决策点 | 默认 | 一句话理由 |
|---|---|---|
| ID | MySQL 用 `IDENTITY`;PostgreSQL 用 `SEQUENCE`(allocationSize=50) | IDENTITY 禁用批量 insert,PG 没理由不用 SEQUENCE |
| 枚举 | `@Enumerated(EnumType.STRING)` | ORDINAL 插一个枚举值历史数据全错位 |
| 时间戳 | `Instant` + `@CreatedDate/@LastModifiedDate` 审计 | UTC 无时区歧义 |
| 命名 | 表/列/索引名全部显式小写下划线 | 不被隐式命名策略变化牵连 |
| 关联 fetch | 一律 `LAZY`(`@ManyToOne`/`@OneToOne` 默认 EAGER,必须手写) | EAGER 是 N+1 头号来源 |
| 跨聚合引用 | 存外键 id,不建对象关联 | 别把别的模块实体图拖进来 |
| `@OneToMany` 集合 | `List` + 双向 + 辅助方法同步两侧 | Set 逼着子实体写 equals/hashCode |
| `@ManyToMany` | 默认改建中间实体;硬要用则必须 `Set` | 中间表迟早要加字段;List 是 bag 会整表重写 |
| Lombok | 只用 `@Getter/@Setter`;禁 `@Data` | @Data 的 equals/toString 踩懒加载雷 |
| equals/hashCode | 只认 id 的 proxy-safe 手写模式 | 代理类与 null id 两个坑 |
| 读路径 | 接口投影或 record DTO,不返回实体 | 不碰实体图就没有懒加载问题 |
| 并发 | 实体带 `@Version` 乐观锁;库存/余额类才上悲观锁 | 冲突低频时乐观锁零成本 |
| 事务 | Service 层,读方法 `readOnly = true` | 边界即用例;readOnly 免脏检查 |
| open-in-view | `false`,显式配置 | OSIV 占死连接、把 N+1 藏进序列化层 |
| DDL | Flyway/Liquibase;`ddl-auto: validate` | 生产 schema 必须有版本历史 |

## 高频事故速查

1. **列表接口慢、日志一屏相同 SQL** → N+1:读路径换投影,要实体就 join fetch /
   `@EntityGraph`;全局配 `default_batch_fetch_size: 100` 兜底 → relationships.md
2. **`LazyInitializationException`** → 在 Service 事务内取完数据组装 DTO;
   禁改 EAGER、禁开 open-in-view 硬扛 → transactions-and-locking.md
3. **join fetch 集合 + 分页** → Hibernate 内存分页(日志 HHH90003004),两步查询:
   先分页查 id 再按 id fetch → relationships.md
4. **`@Transactional` 不生效** → 自调用 / 非 public / 换线程,三大代理失效场景
   → transactions-and-locking.md
5. **`@Modifying` 批量后读到旧数据** → 绕过了一级缓存和 @Version,
   `clearAutomatically = true` + SQL 里手写 version/audit 字段 → repositories-and-queries.md
6. **用 DTO 假装实体去 `save()`** → merge 整行覆盖,并发丢更新;
   更新永远「查托管实体 → 改 setter」,不需要再 save → transactions-and-locking.md
7. **`MultipleBagFetchException`** → 一条查询 fetch 两个 List,拆两条查询或改 Set
   → relationships.md
8. **批量 insert 没变快** → IDENTITY 主键 batch 失效;SEQUENCE + `jdbc.batch_size` +
   `order_inserts`,MySQL 再加 `rewriteBatchedStatements=true` → performance-and-config.md
9. **乐观锁重试永远失败** → 拿旧实体重试;每次重试必须重新查询 → transactions-and-locking.md
10. **软删除后唯一约束挡住重建** → 唯一索引改部分索引或纳入删除时间戳 → entity-design.md

## 参考文件索引

| 任务 | 读 |
|---|---|
| 新建/修改实体:ID、字段映射、Lombok、equals/hashCode、审计、软删除、继承 | [references/entity-design.md](references/entity-design.md) |
| 设计关联:@ManyToOne/@OneToMany/@ManyToMany/@OneToOne、List vs Set、N+1 治理 | [references/relationships.md](references/relationships.md) |
| Repository、派生查询、@Query、@Modifying、投影、分页/滚动、Specification、@EntityGraph、流式读 | [references/repositories-and-queries.md](references/repositories-and-queries.md) |
| @Transactional 语义与失效场景、传播、脏检查与 save、乐观/悲观锁、LazyInitializationException、open-in-view | [references/transactions-and-locking.md](references/transactions-and-locking.md) |
| 配置基线、SQL 日志诊断、批量写、缓存、HikariCP、Flyway、何时绕开 JPA | [references/performance-and-config.md](references/performance-and-config.md) |

按任务读对应文件即可,不必全读。写完代码后自查两条:这个接口发了几条 SQL?
事务边界里有没有慢活(外部调用/大循环)?

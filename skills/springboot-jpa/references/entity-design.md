# 实体设计

写实体前先扫项目里已有的 2~3 个实体，跟它们的约定走（ID 策略、Lombok 用法、命名显隐式）。
以下默认值只在项目没有既有约定时使用。

## 实体骨架

```java
@Entity
@Table(name = "orders", indexes = {
    @Index(name = "idx_orders_user_id", columnList = "user_id"),
    @Index(name = "idx_orders_status_created_at", columnList = "status, created_at")
})
@EntityListeners(AuditingEntityListener.class)
@Getter @Setter
public class Order {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "order_no", nullable = false, unique = true, length = 32)
    private String orderNo;

    @Enumerated(EnumType.STRING)
    @Column(name = "status", nullable = false, length = 20)
    private OrderStatus status = OrderStatus.CREATED;

    @Column(name = "amount", nullable = false, precision = 12, scale = 2)
    private BigDecimal amount;

    @Version
    @Column(name = "version", nullable = false)
    private Long version;

    @CreatedDate
    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    @LastModifiedDate
    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;
}
```

要点：

- **表名、列名、索引名全部显式写出**（小写下划线）。不依赖隐式命名策略——换命名策略或升级
  Hibernate 时隐式名可能变，显式名永远稳定，DBA 拿到 DDL 也能直接对上。
- 常用过滤列（状态、外键、业务号）在 `@Table(indexes=...)` 里声明索引，复合索引列序要
  匹配查询模式（等值列在前、范围/排序列在后）。注意：这些索引声明只在 Hibernate 建表时生效，
  生产的真实索引以 Flyway/Liquibase 迁移脚本为准，两边要一致。
- JPA 要求实体有无参构造器（Hibernate 要求至少 `protected`）。用 Lombok 时注意
  `@Builder` 必须搭配 `@NoArgsConstructor` + `@AllArgsConstructor`，否则会把无参构造器顶掉。

## ID 策略

| 策略 | 写法 | 适用 | 代价 |
|---|---|---|---|
| `IDENTITY` | `Long` + `@GeneratedValue(strategy = IDENTITY)` | MySQL 自增 | **禁用 JDBC 批量 insert**（Hibernate 必须逐条 insert 拿回主键） |
| `SEQUENCE` | `Long` + `@GeneratedValue(strategy = SEQUENCE, generator = "order_seq")` + `@SequenceGenerator(name = "order_seq", sequenceName = "order_seq", allocationSize = 50)` | PostgreSQL / Oracle | 需要建 sequence；`allocationSize` 要和数据库 sequence 的 increment 一致 |
| `UUID` | `UUID` + `@GeneratedValue(strategy = UUID)`（Hibernate 也可用 `@UuidGenerator`） | 分布式、客户端生成、避免 ID 可猜 | 随机 UUID 作聚簇主键会打散 B+ 树写入局部性（MySQL InnoDB 尤甚）；PostgreSQL 用原生 `uuid` 列类型 |

默认：MySQL 用 `IDENTITY`，PostgreSQL 用 `SEQUENCE`（每表独立 sequence）。
需要大批量 insert 的表不要用 `IDENTITY`（见 performance-and-config.md 的批量写入）。

## 字段映射规则

- **枚举一律 `@Enumerated(EnumType.STRING)`**。`ORDINAL` 在枚举中间插值时会静默错位，
  历史数据全错。列长度给够（`length = 20` 起）。
- **`BigDecimal` 必须显式 `precision` + `scale`**，否则落到数据库方言默认值，跨库不一致且可能丢精度。
- **时间戳用 `Instant`**（UTC，无时区歧义）；业务日期用 `LocalDate`。避免 `java.util.Date`/`Calendar`。
- 大文本/二进制：`@Lob`；MySQL 长文本也可以直接 `@Column(columnDefinition = "TEXT")`。
- JSON 列（Hibernate 6+）：

  ```java
  @JdbcTypeCode(SqlTypes.JSON)
  @Column(name = "ext", columnDefinition = "json")
  private Map<String, Object> ext;
  ```

- 值对象用 `@Embeddable` + `@Embedded`，同一实体嵌两份时用 `@AttributeOverrides` 区分列名。
- 布尔列显式 `nullable = false` 并给默认值，避免三态布尔。

## Lombok 与 JPA 的安全搭配

| 注解 | 用不用 | 原因 |
|---|---|---|
| `@Getter` `@Setter` | ✅ 类级 | 无副作用 |
| `@NoArgsConstructor` | ✅ 需要时（配 `@Builder`） | JPA 必需无参构造器 |
| `@Data` | ❌ 禁 | 连带生成的 equals/hashCode/toString 全踩关联字段的懒加载雷 |
| `@EqualsAndHashCode`（默认） | ❌ 禁 | 遍历全部字段：触发懒加载、破坏代理相等性 |
| `@ToString`（默认） | ❌ 禁 | 遍历关联字段触发懒加载，日志一打就 `LazyInitializationException` |
| `@Builder` | ⚠️ 可用 | 必须同时有 `@NoArgsConstructor` + `@AllArgsConstructor` |

要用 Lombok 生成 equals/hashCode 时只认主键：
`@EqualsAndHashCode(onlyExplicitlyIncluded = true)` + 在 `id` 上 `@EqualsAndHashCode.Include`。
但注意 Lombok 版本不处理 Hibernate 代理类差异，跨代理比较要用下面的手写模式。

## equals / hashCode（proxy-safe 手写模式）

懒加载代理的 `getClass()` 是子类，直接比 class 会把同一行数据判为不相等；新实体 `id == null`
时放进 `Set` 再持久化，hashCode 变了会导致集合行为错乱。标准解法：

```java
@Override
public final boolean equals(Object o) {
    if (this == o) return true;
    if (o == null) return false;
    Class<?> oEffectiveClass = o instanceof HibernateProxy proxy
        ? proxy.getHibernateLazyInitializer().getPersistentClass() : o.getClass();
    Class<?> thisEffectiveClass = this instanceof HibernateProxy proxy
        ? proxy.getHibernateLazyInitializer().getPersistentClass() : this.getClass();
    if (thisEffectiveClass != oEffectiveClass) return false;
    Order other = (Order) o;
    return getId() != null && Objects.equals(getId(), other.getId());
}

@Override
public final int hashCode() {
    return this instanceof HibernateProxy proxy
        ? proxy.getHibernateLazyInitializer().getPersistentClass().hashCode()
        : getClass().hashCode();
}
```

- hashCode 返回常量（class 的 hashCode）是**故意的**：保证实体在持久化前后（id 从 null 变有值）
  hash 不变，能安全放进 `HashSet`。集合大了有碰撞代价，所以关联集合优先 `List`（见 relationships.md）。
- `toString()` 只包含非关联字段，理由同上——别在日志里触发懒加载。

## 审计字段

```java
@Configuration
@EnableJpaAuditing
class JpaAuditConfig {
    // 需要 @CreatedBy/@LastModifiedBy 时提供当前用户
    @Bean
    AuditorAware<String> auditorAware() {
        return () -> Optional.ofNullable(SecurityContextHolder.getContext().getAuthentication())
                .map(Authentication::getName);
    }
}
```

实体上 `@EntityListeners(AuditingEntityListener.class)` + `@CreatedDate` / `@LastModifiedDate` /
`@CreatedBy` / `@LastModifiedBy`。多个实体共用时抽成 `@MappedSuperclass` 基类
（`BaseEntity`：id + version + 审计四件套）。

## 软删除

Hibernate 6.4+ 原生注解，一行搞定（查询自动过滤、delete 自动改 update）：

```java
@Entity
@SoftDelete(columnName = "deleted")   // 也可 strategy = TIMESTAMP（6.6+）记删除时间
public class Order { ... }
```

旧版本（Hibernate 6.3 及以下）用组合：

```java
@SQLDelete(sql = "update orders set deleted = true where id = ? and version = ?")
@SQLRestriction("deleted = false")    // @Where 已废弃，别再用
```

注意：软删除后**唯一约束会挡住重建同名数据**，唯一索引要改成部分索引
（如 PostgreSQL `... where deleted = false`）或把删除时间戳纳入唯一键。

## 继承与公共字段

- 公共字段（id、version、审计）→ `@MappedSuperclass`，不产生表。
- 真正的多态持久化才用 `@Inheritance`：默认 `SINGLE_TABLE`（查询快、列全可空），
  `JOINED` 正规化但查询全是 join。没有多态查询需求就别用继承，组合 + 独立表更直白。

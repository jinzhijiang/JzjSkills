# Repository 与查询

版本基线：Spring Boot 3.x 对应 Spring Data JPA 3.x，Boot 4 对应 4.x。
下文标注「3.1+」「4.0+」的是较新 API，老项目用前先确认版本。

## Repository 接口

```java
public interface OrderRepository extends JpaRepository<Order, Long> {}
```

- 日常直接 `JpaRepository`。想收窄暴露面（比如禁止 deleteAll）时，继承
  `Repository<T, ID>` 只声明需要的方法。
- Repository 上不放 `@Transactional`：`SimpleJpaRepository` 自带（读方法 readOnly），
  业务事务边界在 Service 层。
- 通用逻辑复用：`@NoRepositoryBean` 泛型基接口 + JPQL 里 `#{#entityName}` 占位。

## 派生查询（方法名生成）

```java
Optional<Order> findByOrderNo(String orderNo);
List<Order> findByStatusAndCreatedAtAfter(OrderStatus status, Instant since);
boolean existsByOrderNo(String orderNo);
long countByStatus(OrderStatus status);
List<Order> findTop10ByStatusOrderByCreatedAtDesc(OrderStatus status);
List<Order> findByStatus(OrderStatus status, Limit limit);   // 3.2+ 动态限量，不能和 Top 混用
```

- 条件超过 2~3 个就别再堆方法名了，换 `@Query` 或 Specification——
  `findByAAndBOrCAndD` 谁也读不懂优先级。
- `Containing/StartingWith/EndingWith` 会自动转义用户输入里的 `%`/`_`；
  自拼 `Like` 不转义，用户输入进 like 一律优先前三者。
- 嵌套属性有歧义时用下划线显式分割：`findByAddress_ZipCode`。
- `findById/existsById/deleteById` 是保留名，永远指向 `@Id` 属性。
- **`Distinct` 陷阱**：`countDistinctByLastname` 数的是 distinct id，不是 distinct 列值；
  要按列值去重必须手写 `@Query`。
- **派生 `deleteBy...` 是先查后逐条删**（会触发级联和 `@PreRemove` 回调，大数据量把实体全捞进内存）；
  要批量删用 `@Modifying` 的 JPQL delete（不触发回调），二者语义不同，按需选。

## @Query

```java
@Query("select o from Order o where o.status = :status and o.createdAt >= :since")
Page<Order> findRecent(@Param("status") OrderStatus status, @Param("since") Instant since, Pageable pageable);
```

- 位置参数 `?1` 易错难重构，一律命名参数。
- 原生 SQL：`@Query(nativeQuery = true)`，4.0+ 可用组合注解 `@NativeQuery`。
  **原生查询 + 分页必须显式给 `countQuery`**（复杂 SQL 框架改写不了）；
  原生查询的 `Sort` 改写同样只支持简单查询。
- 排序传函数会被拒（防注入）；确实需要时 `JpaSort.unsafe("LENGTH(name)")`，
  或在 JPQL 里起别名后按别名排。
- 返回杂表数据可以直接 `List<Map<String, Object>>`（原生查询），比定义一次性 DTO 省事。

## @Modifying（批量 update/delete）

```java
@Modifying(clearAutomatically = true)
@Query("update Order o set o.status = :to, o.version = o.version + 1 where o.status = :from")
int migrateStatus(@Param("from") OrderStatus from, @Param("to") OrderStatus to);
```

- 只有配 `@Query` 的写操作才需要 `@Modifying`；返回 `int` 拿受影响行数。
- 批量语句**绕过一级缓存、实体回调和 `@Version`**：
  - `clearAutomatically = true` 清掉一级缓存里的过期实体（注意会连带丢弃未 flush 的挂起变更，
    必要时配 `flushAutomatically = true` 先刷）；
  - 乐观锁实体要在 SQL 里手写 `version = version + 1`；
  - 审计字段不会自动更新，要手写 `updatedAt = :now`。
- 需要事务：单独调用时在 Service 方法上加 `@Transactional`。

## 投影（读路径首选）

**接口投影（closed projection）**——只 select 声明的列：

```java
public interface OrderSummary {
    Long getId();
    String getOrderNo();
    OrderStatus getStatus();
}
Page<OrderSummary> findByStatus(OrderStatus status, Pageable pageable);
```

**record DTO 投影**——列名按构造器参数名匹配：

```java
public record OrderSummaryDto(Long id, String orderNo, OrderStatus status) {}

// 派生查询直接返回 record；@Query 返回 record 时（4.0+）
// select o.id, o.orderNo, o.status 会被自动改写成 constructor expression
List<OrderSummaryDto> findByStatus(OrderStatus status);
```

注意事项：

- **open projection（`@Value("#{target.a + target.b}")`）会加载完整实体**，失去投影意义，
  计算逻辑用接口 default 方法写，别用 SpEL。
- DTO 投影的 `@Query` 里**不能给列起别名**（constructor expression 不认别名；接口投影反而需要别名对齐）。
- 投影里放嵌套关联属性会物化整个 join，嵌套层级越浅越好。
- 动态投影：`<T> List<T> findByStatus(OrderStatus status, Class<T> type)`，
  同一查询按调用方选实体/摘要/详情。

## 分页与滚动

| 方式 | 返回 | 代价 | 适用 |
|---|---|---|---|
| `Pageable` | `Page<T>` | 每页额外一条 count | 后台管理页（要总数） |
| `Pageable` | `Slice<T>` | 取 pageSize+1 判断有无下页，无 count | 移动端瀑布流 |
| offset 滚动 3.1+ | `Window<T>` | 无 count；深翻页仍慢 | 顺序批处理 |
| keyset 滚动 3.1+ | `Window<T>` | 走索引，深翻页不退化 | 无限下拉、导出遍历 |

```java
// keyset 滚动：派生查询 + WindowIterator
WindowIterator<Order> it = WindowIterator.of(
        pos -> repo.findFirst100ByStatusOrderByCreatedAtDescIdDesc(status, pos))
    .startingAt(ScrollPosition.keyset());
```

keyset 的硬性要求：排序属性非空、有索引、**排序用到的属性必须出现在查询结果里**
（投影必须包含它们）；字符串 `@Query` 方法目前不支持滚动，用派生查询/Specification。
不用新 API 的项目，游标分页手写 `where (created_at, id) < (:ts, :id) order by created_at desc, id desc` 等价。

`Pageable` 从 Controller 透传时要设防：`@PageableDefault(size = 20)` +
`spring.data.web.pageable.max-page-size` 限上限，别让调用方一页拉十万条。

## Specification（动态条件查询）

repository 加 `extends JpaSpecificationExecutor<Order>`。条件写成静态工厂再组合：

```java
public class OrderSpecs {
    public static Specification<Order> hasStatus(OrderStatus s) {
        return (root, query, cb) -> cb.equal(root.get("status"), s);
    }
    public static Specification<Order> createdAfter(Instant t) {
        return (root, query, cb) -> cb.greaterThanOrEqualTo(root.get("createdAt"), t);
    }
}

var spec = OrderSpecs.hasStatus(status).and(OrderSpecs.createdAfter(since));
Page<Order> page = repo.findAll(spec, pageable);
```

- 动态拼条件（搜索表单一堆可选项）是 Specification 的主场；固定条件写 `@Query` 更直白。
- 配 JPA Metamodel Generator 后用 `Order_.status` 代替字符串，重构安全。
- 4.0+ 新增：`UpdateSpecification`/`DeleteSpecification`（动态批量改删）、
  fluent API `repo.findBy(spec, q -> q.as(OrderSummary.class).sortBy(sort).page(pageable))`
  ——投影 + 动态条件可以这样组合；`q.stream()` 记得关闭。
- 简单等值匹配的备选是 Query by Example，但它不支持范围条件，能力天花板低，一般直接上 Specification。

## @EntityGraph

```java
@EntityGraph(attributePaths = {"items", "user"})
Optional<Order> findWithGraphById(Long id);
```

不写 JPQL 就能声明抓取路径，适合「同一个派生查询，某个入口要带关联」的场景。
和 join fetch 一样受「集合 fetch + 分页」限制（见 relationships.md）。

## 流式与批量读

```java
@Transactional(readOnly = true)   // Stream 必须在事务内消费
public void export(OrderStatus status) {
    try (Stream<Order> stream = repo.streamByStatus(status)) {
        stream.forEach(this::write);
    }
}
```

- `Stream<T>` 走游标逐条取，**必须 try-with-resources + 在事务内**。
- 大遍历时一级缓存会持续膨胀，纯读场景每 N 条 `entityManager.clear()`，
  或改用 keyset `WindowIterator`（天然分批，无缓存膨胀）。

## 自定义实现（fragment）

派生查询和 Specification 都不够用时（复杂报表、CTE、窗口函数）：

```java
public interface OrderRepositoryCustom {
    List<OrderStat> statByDay(Instant from, Instant to);
}
public class OrderRepositoryCustomImpl implements OrderRepositoryCustom {
    @PersistenceContext
    private EntityManager em;
    // em.createNativeQuery(...) 自由发挥
}
public interface OrderRepository extends JpaRepository<Order, Long>, OrderRepositoryCustom {}
```

命名约定：实现类必须叫 `接口名 + Impl`（或配置 `repositoryImplementationPostfix`）。
真到了大量原生 SQL 报表的程度，考虑该模块换 JOOQ/JdbcClient，别硬用 JPA。

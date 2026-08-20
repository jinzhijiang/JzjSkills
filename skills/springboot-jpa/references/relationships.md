# 关联关系与 N+1

## 第一问：真的需要对象关联吗

跨聚合/跨模块的引用**优先存外键 id**（`private Long userId`），不建对象关联：

- 不会误触懒加载，不会把另一个模块的实体图拖进当前事务
- 查询要 join 时用 `@Query` 显式写，成本看得见

只有真正的父子组合关系（订单-明细、文章-评论这类同生共死的）才值得建双向 `@OneToMany`。

## @ManyToOne（多对一）

```java
@ManyToOne(fetch = FetchType.LAZY)   // 默认是 EAGER，必须手动改 LAZY
@JoinColumn(name = "user_id", nullable = false)
private User user;
```

- **`@ManyToOne` / `@OneToOne` 的 JPA 默认是 `EAGER`，每个都要手写 `fetch = FetchType.LAZY`**。
  这是 N+1 的头号来源。
- `@JoinColumn(name=...)` 显式写。
- **不加 cascade**——多对一指向的是独立存在的数据，级联删除/保存它属于事故。
- 只有外键值、不需要对象时，用 `repo.getReferenceById(id)` 拿代理设进去，不发 select。

## @OneToMany（一对多）

只用于父子组合关系，**双向 + mappedBy**（单向 @OneToMany 会产生中间表或对子表外键做额外 update）：

```java
// 父侧（Order）
@OneToMany(mappedBy = "order", cascade = CascadeType.ALL, orphanRemoval = true)
private List<OrderItem> items = new ArrayList<>();

public void addItem(OrderItem item) {
    items.add(item);
    item.setOrder(this);
}
public void removeItem(OrderItem item) {
    items.remove(item);
    item.setOrder(null);
}

// 子侧（OrderItem）——外键的拥有方
@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(name = "order_id", nullable = false)
private Order order;
```

- `cascade = ALL` + `orphanRemoval = true` **仅限组合关系**：子实体离开父亲就没有意义时才用。
- 双向关联必须用 `addItem/removeItem` 这类辅助方法同步两侧，只设一边会出现内存图和数据库不一致。
- 集合在字段上初始化（`new ArrayList<>()`），永不为 null；不要提供 `setItems`，
  要替换内容用 `clear()` + `addAll`，直接换引用会破坏 orphanRemoval 的脏检查。

### List 还是 Set

| | `List` | `Set`（`LinkedHashSet` 初始化） |
|---|---|---|
| equals/hashCode | 子实体可以不写 | 子实体**必须**写 proxy-safe 版 |
| 去重语义 | 无 | 有 |
| bag 语义 | 无 `@OrderColumn` 时是 bag：一次 fetch 两个 List 集合会抛 `MultipleBagFetchException` | 无此问题 |

默认用 `List`（少写 equals/hashCode、hashCode 常量化的碰撞问题也不存在）；
需要去重语义或同实体有多个集合要 join fetch 时换 `Set`。

## @ManyToMany（多对多）

```java
@ManyToMany
@JoinTable(name = "article_tags",
    joinColumns = @JoinColumn(name = "article_id"),
    inverseJoinColumns = @JoinColumn(name = "tag_id"))
private Set<Tag> tags = new LinkedHashSet<>();
```

- **必须用 `Set`**：`List` 是 bag，改动一个元素 Hibernate 会整表 delete + insert。
- `@JoinTable` 显式写全三个名字。
- 中间表一旦要加字段（排序、时间、备注——迟早会要），`@ManyToMany` 就得推倒重来。
  **默认建议直接建中间实体** `ArticleTag`，两边 `@ManyToOne`，从一开始就留好扩展位。
- 禁用 `CascadeType.REMOVE`：删一篇文章不应该删掉 Tag 本身。

## @OneToOne（一对一）

- 非拥有方（`mappedBy` 侧）的 `@OneToOne` **LAZY 不生效**（Hibernate 不知道该给代理还是 null，
  只能立即查），除非开字节码增强。
- 首选方案：**共享主键 + `@MapsId`**，子表主键即外键，天然唯一且省一列：

```java
@Entity
public class UserProfile {
    @Id
    private Long id;

    @OneToOne(fetch = FetchType.LAZY)
    @MapsId
    @JoinColumn(name = "user_id")
    private User user;
}
```

反向不建关联，需要时 `profileRepo.findById(userId)` 直接查——`@OneToOne` 尽量只保留一个方向。

## N+1：识别与治理

**识别**：开发环境打开 SQL 日志（见 performance-and-config.md），列表接口出现
「1 条主查询 + N 条相同形状的子查询」即中招。可加保险丝：

```properties
# 分页 + collection fetch 在内存里分页时直接报错，而不是静默拖垮
spring.jpa.properties.hibernate.query.fail_on_pagination_over_collection_fetch=true
```

**治理手段按优先级**：

1. **读路径用 DTO 投影**（见 repositories-and-queries.md）——不碰实体图，天然没有 N+1。
2. **`join fetch`**：明确要实体及其集合时。

   ```java
   @Query("select o from Order o join fetch o.items where o.id = :id")
   Optional<Order> findWithItems(@Param("id") Long id);
   ```

3. **`@EntityGraph`**：不想写 JPQL 时声明式抓取。

   ```java
   @EntityGraph(attributePaths = {"items", "user"})
   Optional<Order> findWithGraphById(Long id);
   ```

4. **批量抓取兜底**：全局配 `spring.jpa.properties.hibernate.default_batch_fetch_size=100`，
   把 N 条懒加载 select 合并成 `in (?, ?, ...)`，治不了根但把 N+1 降成 N/100+1，
   作为全局安全网强烈建议开启。

**join fetch 集合 + 分页 = 坑**：Hibernate 只能查全量再在内存里分页
（日志出现 `HHH90003004: firstResult/maxResults specified with collection fetch; applying in memory`）。
分页场景的正确姿势是两步查询：

```java
// 第一步：只分页查 id（或投影）
Page<Long> ids = repo.findIdsByStatus(status, pageable);
// 第二步：按 id 批量 join fetch，再按原顺序组装
List<Order> orders = repo.findWithItemsByIdIn(ids.getContent());
```

多对一（单值关联）的 join fetch 不受此限制，可以放心和分页一起用。

**`MultipleBagFetchException`**：一条查询 join fetch 两个 `List` 集合时抛出。
解法：拆成两条查询分别 fetch（Hibernate 会按一级缓存合并到同一实体图），或把其中一个集合改 `Set`。
不要用 `Stream.distinct()`/`DISTINCT` 硬压笛卡尔积——数据量一大就爆。

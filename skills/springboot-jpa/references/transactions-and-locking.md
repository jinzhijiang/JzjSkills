# 事务与锁

## @Transactional 基本盘

- **放在 Service 层的 public 方法上**，Repository 和 Controller 都不放。
  一个业务用例一个事务边界，DTO 组装在边界内完成（出了边界懒加载就断了）。
- **读路径 `@Transactional(readOnly = true)`**：Hibernate 跳过脏检查快照、flush 模式设为
  MANUAL，省内存省 CPU；连接可被路由到只读库。常见做法是类级 `readOnly = true`，
  写方法上再单独标 `@Transactional`。
- **事务要短**：外部 HTTP 调用、MQ 发送、文件 IO 不要包在事务里——连接被占着，池子很快耗干。
  先落库、后发消息；要一致性用事务性发件箱（outbox）模式，别拉长数据库事务。

## 回滚规则

默认**只回滚 unchecked 异常**（`RuntimeException`/`Error`），checked 异常不回滚。
业务异常统一继承 `RuntimeException` 最省心；必须抛 checked 时显式声明：

```java
@Transactional(rollbackFor = Exception.class)
```

在事务方法里 catch 异常又不重新抛出时，事务照常提交——如果代理层已经标记了 rollback-only
（比如内层 REQUIRED 事务抛过异常被你吞了），提交时会抛 `UnexpectedRollbackException`。
不要吞内层事务的异常。

## 代理机制的三个失效场景

Spring 事务靠代理实现，以下情况注解**静默失效**（没有报错，只是没有事务）：

1. **自调用**：同类内 `this.methodB()` 不走代理。要拆类，或注入自身代理（`ObjectProvider<自身>`）。
2. **非 public 方法**：代理只拦 public。
3. **方法内 new 线程 / CompletableFuture**：事务绑定在 ThreadLocal，新线程没有事务。

怀疑事务没生效时开 `logging.level.org.springframework.transaction.interceptor=TRACE` 看进出日志。

## 传播行为

- 默认 `REQUIRED`（有就加入、没有就新建），95% 的场景就用它，**不确定时不要乱设**。
- `REQUIRES_NEW`：挂起外层、新开事务新占一个连接。外层持连接等内层，池子小并发高时会**自死锁**
  （所有线程都拿着外层连接等内层连接）。只用于「无论外层成败都要落库」的场景（审计日志、流水记录）。
- `NESTED`：靠 savepoint 局部回滚，JPA 下支持有限，少用。
- `SUPPORTS`/`NOT_SUPPORTED`/`MANDATORY`/`NEVER`：明确知道为什么才用。

## 脏检查与 save 的语义

事务内查出来的实体是**托管态**：改 setter 即可，提交时自动 flush update，
**不需要也不应该再调 `repo.save(entity)`**：

```java
@Transactional
public void updateStatus(Long id, OrderStatus status) {
    Order order = repo.findById(id).orElseThrow(() -> new OrderNotFoundException(id));
    order.setStatus(status);   // 到此为止，提交时自动 update
}
```

`save()` 的真正语义：新实体 persist、游离实体 merge。merge 会先 select 再整行 update，
把「反序列化出来的 DTO 假装成实体去 save」是常见的性能与覆盖事故（并发下互相覆盖字段）。
更新永远走「查出托管实体 → 改字段」。

## 乐观锁（默认并发策略）

实体加 `@Version`（`Long` 或 `Integer`，Hibernate 自动维护）：

- 每次 update 带 `where version = ?`，不匹配抛
  `ObjectOptimisticLockingFailureException`（Spring 包装后的）。
- Web 请求场景：捕获后转 409 Conflict 让前端重试/刷新。
- 后台任务场景：用 `@Retryable` 或手写重试循环，**重试必须重新查询实体**，拿旧对象重试永远失败。
- 注意：`@Modifying` 的 bulk update **绕过版本机制**（不自增 version、不做版本检查），
  混用时要在 JPQL 里手写 `version = version + 1`。

## 悲观锁（真金白银才用）

库存扣减、余额变动这类「冲突常态化、重试代价高」的场景用行锁：

```java
@Lock(LockModeType.PESSIMISTIC_WRITE)
@QueryHints(@QueryHint(name = "jakarta.persistence.lock.timeout", value = "3000"))
@Query("select a from Account a where a.id = :id")
Optional<Account> findByIdForUpdate(@Param("id") Long id);
```

- 生成 `select ... for update`，同行并发事务阻塞排队。
- **必须设锁超时**，否则慢事务把等待线程全挂住；超时抛 `PessimisticLockingFailureException`。
  锁超时 hint 的支持因数据库而异（PostgreSQL/Oracle 支持，MySQL 8 走 `innodb_lock_wait_timeout`）。
- 多行加锁要**按固定顺序**（如按 id 排序）获取，避免死锁。
- 纯计数类更新可以不加锁，直接原子 update：
  `@Modifying @Query("update Stock s set s.qty = s.qty - :n where s.id = :id and s.qty >= :n")`，
  返回受影响行数为 0 即失败，一条 SQL 天然原子。

## LazyInitializationException 的正确处理

出现 `could not initialize proxy - no Session` 时，**三个不要**：

- 不要把关联改成 `EAGER`——全局性能代价换一处报错消失。
- 不要开 `spring.jpa.open-in-view=true` 硬扛——见下。
- 不要在 Controller 里补 `@Transactional`——事务边界漂到了 Web 层。

正确做法：在 Service 的事务边界内把数据取完整——读路径用 DTO 投影，
需要实体图时 `join fetch` / `@EntityGraph` 一次取够，出边界前组装成 DTO。

## open-in-view 关掉

```properties
spring.jpa.open-in-view=false
```

OSIV 让 Session 活到视图渲染结束：数据库连接被占满整个请求周期（包括调外部接口的时间），
懒加载在 Controller/序列化层随处可触发，把 N+1 藏到监控死角。Boot 启动时的
`spring.jpa.open-in-view is enabled by default` 警告就是在劝你关掉。
关掉后所有懒加载问题会在开发期暴露成异常，逼着数据获取回到 Service 层——这是好事。
新项目一律显式关闭；老项目关闭前先全量回归，会炸出一批隐藏的懒加载点，逐个改成投影或 fetch。

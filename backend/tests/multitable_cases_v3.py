"""50 fixed Chinook questions with independently written reference SQL."""

CASES = []


def add(category, question, tables, sql):
    CASES.append({'category': category, 'question': question,
                  'expected_tables': tables, 'reference_sql': sql})


CI = ' FROM customer c JOIN invoice i ON c.CustomerId=i.CustomerId'
AA = ' FROM artist a JOIN album b ON a.ArtistId=b.ArtistId'
GT = ' FROM genre g JOIN track t ON g.GenreId=t.GenreId'
EC = ' FROM employee e JOIN customer c ON e.EmployeeId=c.SupportRepId'
GTL = GT + ' JOIN invoiceline l ON t.TrackId=l.TrackId'
AAT = AA + ' JOIN track t ON b.AlbumId=t.AlbumId'
ATL = ' FROM album a JOIN track t ON a.AlbumId=t.AlbumId JOIN invoiceline l ON t.TrackId=l.TrackId'
CIL = CI + ' JOIN invoiceline l ON i.InvoiceId=l.InvoiceId'

# 20 two-table cases.
add('two_table', '所有客户一共消费了多少钱？', ['customer','invoice'], 'SELECT SUM(i.Total)'+CI)
add('two_table', '美国客户消费总额是多少？', ['customer','invoice'], "SELECT SUM(i.Total)"+CI+" WHERE c.Country='USA'")
add('two_table', '加拿大客户消费总额是多少？', ['customer','invoice'], "SELECT SUM(i.Total)"+CI+" WHERE c.Country='Canada'")
add('two_table', '所有客户共有多少张订单？', ['customer','invoice'], 'SELECT COUNT(i.InvoiceId)'+CI)
add('two_table', '美国客户有多少张订单？', ['customer','invoice'], "SELECT COUNT(i.InvoiceId)"+CI+" WHERE c.Country='USA'")
add('two_table', '加拿大客户有多少张订单？', ['customer','invoice'], "SELECT COUNT(i.InvoiceId)"+CI+" WHERE c.Country='Canada'")
add('two_table', '客户订单的平均金额是多少？', ['customer','invoice'], 'SELECT AVG(i.Total)'+CI)
add('two_table', '客户订单的最高金额是多少？', ['customer','invoice'], 'SELECT MAX(i.Total)'+CI)
add('two_table', '艺术家一共有多少张专辑？', ['artist','album'], 'SELECT COUNT(b.AlbumId)'+AA)
add('two_table', '歌手 AC/DC 有多少张专辑？', ['artist','album'], "SELECT COUNT(b.AlbumId)"+AA+" WHERE a.Name='AC/DC'")
add('two_table', '歌手 Queen 有多少张专辑？', ['artist','album'], "SELECT COUNT(b.AlbumId)"+AA+" WHERE a.Name='Queen'")
add('two_table', '各艺术家分别有多少张专辑？', ['artist','album'], 'SELECT a.Name,COUNT(b.AlbumId)'+AA+' GROUP BY a.ArtistId,a.Name ORDER BY a.Name LIMIT 100')
add('two_table', '所有音乐类型共有多少首歌曲？', ['genre','track'], 'SELECT COUNT(t.TrackId)'+GT)
add('two_table', 'Rock 音乐类型有多少首歌曲？', ['genre','track'], "SELECT COUNT(t.TrackId)"+GT+" WHERE g.Name='Rock'")
add('two_table', 'Jazz 音乐类型有多少首歌曲？', ['genre','track'], "SELECT COUNT(t.TrackId)"+GT+" WHERE g.Name='Jazz'")
add('two_table', '各音乐类型分别有多少首歌曲？', ['genre','track'], 'SELECT g.Name,COUNT(t.TrackId)'+GT+' GROUP BY g.GenreId,g.Name ORDER BY g.Name LIMIT 100')
add('two_table', '所有员工一共服务多少名客户？', ['employee','customer'], 'SELECT COUNT(c.CustomerId)'+EC)
add('two_table', '员工 Jane 服务多少名客户？', ['employee','customer'], "SELECT COUNT(c.CustomerId)"+EC+" WHERE e.FirstName='Jane'")
add('two_table', '员工 Margaret 服务多少名客户？', ['employee','customer'], "SELECT COUNT(c.CustomerId)"+EC+" WHERE e.FirstName='Margaret'")
add('two_table', '每位员工分别服务多少名客户？', ['employee','customer'], 'SELECT e.FirstName,e.LastName,COUNT(c.CustomerId)'+EC+' GROUP BY e.EmployeeId,e.FirstName,e.LastName ORDER BY e.EmployeeId LIMIT 100')

# 15 three-table cases.
add('three_table', '所有音乐类型歌曲卖出数量合计是多少？', ['genre','track','invoiceline'], 'SELECT SUM(l.Quantity)'+GTL)
add('three_table', 'Rock 类型歌曲卖出数量合计是多少？', ['genre','track','invoiceline'], "SELECT SUM(l.Quantity)"+GTL+" WHERE g.Name='Rock'")
add('three_table', 'Jazz 类型歌曲卖出数量合计是多少？', ['genre','track','invoiceline'], "SELECT SUM(l.Quantity)"+GTL+" WHERE g.Name='Jazz'")
add('three_table', '所有音乐类型的歌曲销量记录有多少条？', ['genre','track','invoiceline'], 'SELECT COUNT(l.InvoiceLineId)'+GTL)
add('three_table', '每种音乐类型卖出的歌曲数量是多少？', ['genre','track','invoiceline'], 'SELECT g.Name,SUM(l.Quantity)'+GTL+' GROUP BY g.GenreId,g.Name ORDER BY g.Name LIMIT 100')
add('three_table', '哪个音乐类型卖出的歌曲数量最多？', ['genre','track','invoiceline'], 'SELECT g.Name,SUM(l.Quantity) AS sold'+GTL+' GROUP BY g.GenreId,g.Name ORDER BY sold DESC LIMIT 1')
add('three_table', '所有艺术家的歌曲一共有多少首？', ['artist','album','track'], 'SELECT COUNT(t.TrackId)'+AAT)
add('three_table', '艺术家 AC/DC 的歌曲有多少首？', ['artist','album','track'], "SELECT COUNT(t.TrackId)"+AAT+" WHERE a.Name='AC/DC'")
add('three_table', '每位艺术家的歌曲数量是多少？', ['artist','album','track'], 'SELECT a.Name,COUNT(t.TrackId)'+AAT+' GROUP BY a.ArtistId,a.Name ORDER BY a.Name LIMIT 100')
add('three_table', '专辑中的歌曲总共卖出多少首？', ['album','track','invoiceline'], 'SELECT SUM(l.Quantity)'+ATL)
add('three_table', '每张专辑卖出的歌曲数量是多少？', ['album','track','invoiceline'], 'SELECT a.Title,SUM(l.Quantity)'+ATL+' GROUP BY a.AlbumId,a.Title ORDER BY a.Title LIMIT 100')
add('three_table', '哪张专辑卖出的歌曲数量最多？', ['album','track','invoiceline'], 'SELECT a.Title,SUM(l.Quantity) AS sold'+ATL+' GROUP BY a.AlbumId,a.Title ORDER BY sold DESC LIMIT 1')
add('three_table', '客户订单明细的购买数量总和是多少？', ['customer','invoice','invoiceline'], 'SELECT SUM(l.Quantity)'+CIL)
add('three_table', '美国客户订单明细的购买数量是多少？', ['customer','invoice','invoiceline'], "SELECT SUM(l.Quantity)"+CIL+" WHERE c.Country='USA'")
add('three_table', '哪个客户的订单明细购买数量最多？', ['customer','invoice','invoiceline'], 'SELECT c.CustomerId,SUM(l.Quantity) AS bought'+CIL+' GROUP BY c.CustomerId ORDER BY bought DESC LIMIT 1')

# 10 grouping/aggregation cases.
add('aggregation', '每个客户的消费总额分别是多少？', ['customer','invoice'], 'SELECT c.CustomerId,SUM(i.Total)'+CI+' GROUP BY c.CustomerId ORDER BY c.CustomerId LIMIT 100')
add('aggregation', '消费最多的客户是谁？', ['customer','invoice'], 'SELECT c.CustomerId,SUM(i.Total) AS spent'+CI+' GROUP BY c.CustomerId ORDER BY spent DESC LIMIT 1')
add('aggregation', '歌手的专辑数分别是多少？', ['artist','album'], 'SELECT a.Name,COUNT(b.AlbumId)'+AA+' GROUP BY a.ArtistId,a.Name ORDER BY a.Name LIMIT 100')
add('aggregation', '哪位歌手拥有的专辑最多？', ['artist','album'], 'SELECT a.Name,COUNT(b.AlbumId) AS total'+AA+' GROUP BY a.ArtistId,a.Name ORDER BY total DESC LIMIT 1')
add('aggregation', '各曲风对应的歌曲数是多少？', ['genre','track'], 'SELECT g.Name,COUNT(t.TrackId)'+GT+' GROUP BY g.GenreId,g.Name ORDER BY g.Name LIMIT 100')
add('aggregation', '哪种音乐类型的歌曲最多？', ['genre','track'], 'SELECT g.Name,COUNT(t.TrackId) AS total'+GT+' GROUP BY g.GenreId,g.Name ORDER BY total DESC LIMIT 1')
add('aggregation', '每位员工服务的客户数量是多少？', ['employee','customer'], 'SELECT e.FirstName,e.LastName,COUNT(c.CustomerId)'+EC+' GROUP BY e.EmployeeId,e.FirstName,e.LastName ORDER BY e.EmployeeId LIMIT 100')
add('aggregation', '哪位员工服务的客户最多？', ['employee','customer'], 'SELECT e.FirstName,e.LastName,COUNT(c.CustomerId) AS total'+EC+' GROUP BY e.EmployeeId,e.FirstName,e.LastName ORDER BY total DESC LIMIT 1')
add('aggregation', '每种音乐类型卖出的歌曲数是多少？', ['genre','track','invoiceline'], 'SELECT g.Name,SUM(l.Quantity)'+GTL+' GROUP BY g.GenreId,g.Name ORDER BY g.Name LIMIT 100')
add('aggregation', '哪种音乐类型销量最高？', ['genre','track','invoiceline'], 'SELECT g.Name,SUM(l.Quantity) AS sold'+GTL+' GROUP BY g.GenreId,g.Name ORDER BY sold DESC LIMIT 1')

# 5 multi-condition cases.
add('complex', '美国客户中消费最高的前 3 位是谁？', ['customer','invoice'], "SELECT c.CustomerId,SUM(i.Total) AS spent"+CI+" WHERE c.Country='USA' GROUP BY c.CustomerId ORDER BY spent DESC LIMIT 3")
add('complex', '加拿大客户中订单最多的前 5 位是谁？', ['customer','invoice'], "SELECT c.CustomerId,COUNT(i.InvoiceId) AS total"+CI+" WHERE c.Country='Canada' GROUP BY c.CustomerId ORDER BY total DESC LIMIT 5")
add('complex', 'Rock 类型销量最高的前 5 首歌曲是什么？', ['genre','track','invoiceline'], "SELECT t.Name,SUM(l.Quantity) AS sold"+GTL+" WHERE g.Name='Rock' GROUP BY t.TrackId,t.Name ORDER BY sold DESC LIMIT 5")
add('complex', 'Jazz 类型销量最高的前 5 首歌曲是什么？', ['genre','track','invoiceline'], "SELECT t.Name,SUM(l.Quantity) AS sold"+GTL+" WHERE g.Name='Jazz' GROUP BY t.TrackId,t.Name ORDER BY sold DESC LIMIT 5")
add('complex', '美国客户的订单平均金额是多少？', ['customer','invoice'], "SELECT AVG(i.Total)"+CI+" WHERE c.Country='USA'")

assert len(CASES) == 50

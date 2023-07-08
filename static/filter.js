    document.getElementById('filterInput').addEventListener('keyup', function() {
        let filterValue = document.getElementById('filterInput').value.toUpperCase();
        let tbody = document.querySelector('.results-table tbody');
        let trs = tbody.getElementsByTagName('tr');
        
        for (let i = 0; i < trs.length; i++) {
            let tds = trs[i].getElementsByTagName('td');
            let found = false;
            for (let j = 0; j < tds.length; j++) {
                let td = tds[j];
                if (td) {
                    let txtValue = td.textContent || td.innerText;
                    if (txtValue.toUpperCase().indexOf(filterValue) > -1) {
                        found = true;
                        break;
                    }
                }
            }
            trs[i].style.display = found ? '' : 'none';
        }
    });

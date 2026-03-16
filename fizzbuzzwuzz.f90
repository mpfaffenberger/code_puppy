program fizzbuzzwuzz
  implicit none

  integer :: i
  character(len=32) :: out

  do i = 1, 105
    out = ""

    if (mod(i, 3) == 0) out = trim(out) // "Fizz"
    if (mod(i, 5) == 0) out = trim(out) // "Buzz"
    if (mod(i, 7) == 0) out = trim(out) // "Wuzz"

    if (len_trim(out) == 0) then
      print '(I0)', i
    else
      print '(A)', trim(out)
    end if
  end do

end program fizzbuzzwuzz

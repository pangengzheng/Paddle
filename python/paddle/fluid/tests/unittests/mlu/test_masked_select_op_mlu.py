#  Copyright (c) 2022 PaddlePaddle Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import unittest
import sys

sys.path.append("..")
import numpy as np
from eager_op_test import OpTest, skip_check_grad_ci
import paddle.fluid as fluid
import paddle

paddle.enable_static()


def np_masked_select(shape, x, mask):
    result = np.empty(shape=(0), dtype=x.dtype)
    sum = 0
    for index, (ele, ma) in enumerate(zip(np.nditer(x), np.nditer(mask))):
        if ma:
            sum = sum + 1
            result = np.append(result, ele)
    for index, (ele, ma) in enumerate(zip(np.nditer(x), np.nditer(mask))):
        if index >= sum:
            result = np.append(result, 0)
    result = np.reshape(result, shape)
    return result


class TestMaskedSelectOp(OpTest):
    def setUp(self):
        self.init()
        self.__class__.use_mlu = True
        self.place = paddle.device.MLUPlace(0)
        self.op_type = "masked_select"
        x = np.random.random(self.shape).astype('float32')
        mask = np.array(np.random.randint(2, size=self.shape, dtype=bool))
        out = np_masked_select(self.shape, x, mask)
        self.inputs = {'X': x, 'Mask': mask}
        self.outputs = {'Y': out}

    def test_check_output(self):
        self.check_output_with_place(self.place)

    def test_check_grad(self):
        self.check_grad_with_place(self.place, ['X'], 'Y')

    def init(self):
        self.shape = (50, 3)


class TestMaskedSelectOp1(TestMaskedSelectOp):
    def init(self):
        self.shape = (6, 8, 9, 18)


class TestMaskedSelectOp2(TestMaskedSelectOp):
    def init(self):
        self.shape = (168,)


@skip_check_grad_ci(reason="get_numeric_gradient not support int32")
class TestMaskedSelectOpInt32(TestMaskedSelectOp):
    def init_dtype(self):
        self.dtype = np.int32

    def test_check_grad(self):
        pass


class TestMaskedSelectOpFp16(TestMaskedSelectOp):
    def init_dtype(self):
        self.dtype = np.float16

    def test_check_grad(self):
        x_grad = self.inputs['Mask'].astype(self.dtype)
        x_grad = x_grad * (1 / x_grad.size)
        self.check_grad_with_place(
            self.place, ['X'], 'Y', user_defined_grads=[x_grad]
        )


class TestMaskedSelectAPI(unittest.TestCase):
    def test_imperative_mode(self):
        paddle.disable_static()
        shape = (88, 6, 8)
        np_x = np.random.random(shape).astype('float32')
        np_mask = np.array(np.random.randint(2, size=shape, dtype=bool))
        x = paddle.to_tensor(np_x)
        mask = paddle.to_tensor(np_mask)
        out = paddle.masked_select(x, mask)
        np_out = np_masked_select(shape, np_x, np_mask)
        self.assertEqual(np.allclose(out.numpy(), np_out), True)
        paddle.enable_static()

    def test_static_mode(self):
        shape = [8, 9, 6]
        x = paddle.static.data(shape=shape, dtype='float32', name='x')
        mask = paddle.static.data(shape=shape, dtype='bool', name='mask')
        np_x = np.random.random(shape).astype('float32')
        np_mask = np.array(np.random.randint(2, size=shape, dtype=bool))

        out = paddle.masked_select(x, mask)
        np_out = np_masked_select(shape, np_x, np_mask)

        exe = paddle.static.Executor(place=paddle.device.MLUPlace(0))

        res = exe.run(
            paddle.static.default_main_program(),
            feed={"x": np_x, "mask": np_mask},
            fetch_list=[out],
        )
        self.assertEqual(np.allclose(res, np_out), True)


class TestMaskedSelectError(unittest.TestCase):
    def test_error(self):
        with paddle.static.program_guard(
            paddle.static.Program(), paddle.static.Program()
        ):

            shape = [8, 9, 6]
            x = paddle.static.data(shape=shape, dtype='float32', name='x')
            mask = paddle.static.data(shape=shape, dtype='bool', name='mask')
            mask_float = paddle.static.data(
                shape=shape, dtype='float32', name='mask_float'
            )
            np_x = np.random.random(shape).astype('float32')
            np_mask = np.array(np.random.randint(2, size=shape, dtype=bool))

            def test_x_type():
                paddle.masked_select(np_x, mask)

            self.assertRaises(TypeError, test_x_type)

            def test_mask_type():
                paddle.masked_select(x, np_mask)

            self.assertRaises(TypeError, test_mask_type)

            def test_mask_dtype():
                paddle.masked_select(x, mask_float)

            self.assertRaises(TypeError, test_mask_dtype)


if __name__ == '__main__':
    unittest.main()
